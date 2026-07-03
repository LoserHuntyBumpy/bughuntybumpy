#!/usr/bin/env python3
"""restore.py - Wiederherstellungspunkt-Tool (Standalone, projektunabhaengig).

Backup-Modell: Post-Run-Snapshot statt Pre-Edit-Backup.
- Basis-Snapshot (-1): voller Projektbaum minus Ignore-Liste.
- W-H-P (-2): Delta aus restore_FILES.md.
- Restore (-3): Echtes Time-Travel via Replay aller Punkte <= Ziel.
- Archiv (--archive / Auto): Hot/Cold-Tiering, alte Punkte in Monats-Zip.

Zentraler Backup-Root (Default ~/.restore_backups, Override via Env
RESTORE_BACKUP_ROOT oder .env-Datei). Pro Projekt ein Unterordner (Default
basename(cwd), Override via Env RESTORE_PROJECT_NAME):

  <BACKUP_ROOT>/<projekt>/
    restore_FILES.md      Staging
    .restoreignore        optional, Glob wie .gitignore
    index.json            aggregierte DB aller Punkte (inkl. storage-Flags)
    <id>/manifest.json    Datei-Liste eines Live-Punkts (Audit-Redundanz)
    <id>/files.zip        Datei-Inhalte (DEFLATE)
    _archive/<YYYY-MM>.zip Cold-Tier: gebuendelte alte Punkte (ZIP_STORED)

Projekt-Root enthaelt vom Workflow nur restore.py.
Punkt-ID = Endzeit des Runs, Format YYYY-MM-DD_HH-MM-SS.
"""

import sys
import os
import io
import json
import shutil
import zipfile
import fnmatch
from datetime import datetime, timedelta

# --- Konstanten -------------------------------------------------------------

ROOT = os.getcwd()


def _load_dotenv():
    """Minimaler .env-Leser (stdlib only). Liest KEY=VALUE aus .env im
    Projekt-Root bzw. neben restore.py. Bereits gesetzte Env-Vars haben
    Vorrang (setdefault). Keine externe Abhaengigkeit."""
    seen = set()
    for cand in (
        os.path.join(ROOT, ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    ):
        if cand in seen or not os.path.isfile(cand):
            continue
        seen.add(cand)
        with open(cand, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)


_load_dotenv()

# Default-Backup-Root portabel (kein maschinen-fester Pfad). Override via
# Env RESTORE_BACKUP_ROOT oder .env-Datei (siehe .env.example).
DEFAULT_BACKUP_ROOT = os.path.join(os.path.expanduser("~"), ".restore_backups")
BACKUP_ROOT = os.environ.get("RESTORE_BACKUP_ROOT", DEFAULT_BACKUP_ROOT)
PROJECT_NAME = os.environ.get(
    "RESTORE_PROJECT_NAME", os.path.basename(ROOT.rstrip("\\/")) or "root"
)
WORKDIR = os.path.join(BACKUP_ROOT, PROJECT_NAME)
BACKUP_DIR = WORKDIR
ARCHIVE_DIR = os.path.join(WORKDIR, "_archive")
INDEX_PATH = os.path.join(WORKDIR, "index.json")
FILES_MD = os.path.join(WORKDIR, "restore_FILES.md")
RESTOREIGNORE = os.path.join(WORKDIR, ".restoreignore")
LEGACY_WORKDIR = os.path.join(ROOT, ".restore")

PAGE_SIZE = 20
ID_FMT = "%Y-%m-%d_%H-%M-%S"

HOT_KEEP = 50        # neueste N Punkte bleiben hot (Einzel-Ordner)
AGE_DAYS = 14        # Punkte aelter -> archivieren
COUNT_TRIGGER = 60   # > so viele Live-Punkte -> Buendelungslauf

# .restore weiter ignoriert: Schutz, falls Legacy-Ordner noch im Baum liegt.
DEFAULT_IGNORE_DIRS = {
    "node_modules", ".venv", "__pycache__", "dist", "build", ".git", ".restore",
}
TOOL_FILES = {"restore.py"}

ACTIONS = ("modified", "created", "deleted")

# --- Exit-Codes -------------------------------------------------------------

EXIT_OK = 0
EXIT_ERR = 1
EXIT_NO_POINT = 2
EXIT_NO_STAGING = 3


def fail(msg, code=EXIT_ERR):
    sys.stderr.write("FEHLER: " + msg + "\n")
    sys.exit(code)


def ensure_workdir():
    os.makedirs(WORKDIR, exist_ok=True)


def migrate_legacy():
    """Verschiebt projektlokales .restore/ (altes Layout) einmalig in den
    zentralen Backup-Root. Idempotent: existiert Ziel-WORKDIR schon, kein
    Move (Legacy bleibt liegen, Nutzer raeumt manuell)."""
    if os.path.isdir(LEGACY_WORKDIR) and not os.path.exists(WORKDIR):
        os.makedirs(BACKUP_ROOT, exist_ok=True)
        shutil.move(LEGACY_WORKDIR, WORKDIR)
        sys.stderr.write("Migriert: %s -> %s\n" % (LEGACY_WORKDIR, WORKDIR))


# --- Pfad-Helfer ------------------------------------------------------------

def to_rel(abs_path):
    return os.path.relpath(abs_path, ROOT).replace(os.sep, "/")


def to_abs(rel):
    return os.path.join(ROOT, rel.replace("/", os.sep))


def load_restoreignore():
    pats = []
    if os.path.isfile(RESTOREIGNORE):
        with open(RESTOREIGNORE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    pats.append(line.rstrip("/"))
    return pats


def _has_glob_meta(pat):
    return any(c in pat for c in "*?[")


def is_ignored(rel, glob_pats):
    parts = rel.split("/")
    if any(p in DEFAULT_IGNORE_DIRS for p in parts):
        return True
    if rel in TOOL_FILES or parts[-1] in TOOL_FILES:
        return True
    for pat in glob_pats:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pat + "/*"):
            return True
        # Eingegrenzter Segment-Match: nur reine Namen (kein Slash, kein
        # Glob-Meta) gegen Verzeichnis-Segmente (parts[:-1]). Trifft so
        # Inhalte gleichnamiger Ordner in jeder Tiefe, aber keine beliebig
        # tiefe gleichnamige Datei.
        if "/" not in pat and not _has_glob_meta(pat):
            if any(p == pat for p in parts[:-1]):
                return True
    return False


def walk_project():
    glob_pats = load_restoreignore()
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [
            d for d in dirnames
            if d not in DEFAULT_IGNORE_DIRS
            and not is_ignored(to_rel(os.path.join(dirpath, d)), glob_pats)
        ]
        for fn in filenames:
            ap = os.path.join(dirpath, fn)
            rel = to_rel(ap)
            if not is_ignored(rel, glob_pats):
                out.append(rel)
    return sorted(out)


# --- Index ------------------------------------------------------------------

def load_index():
    if not os.path.isfile(INDEX_PATH):
        return {"version": 1, "archived_count": 0, "points": []}
    with open(INDEX_PATH, "r", encoding="utf-8") as fh:
        idx = json.load(fh)
    idx.setdefault("archived_count", 0)
    return idx


def save_index(idx):
    ensure_workdir()
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(idx, fh, indent=2, ensure_ascii=False)


def sorted_points(idx):
    return sorted(idx["points"], key=lambda p: p["id"])


def new_id():
    return datetime.now().strftime(ID_FMT)


def recount_archived(idx):
    idx["archived_count"] = sum(
        1 for p in idx["points"] if p.get("storage", "live") == "archived"
    )


def point_storage(idx, pid):
    for p in idx["points"]:
        if p["id"] == pid:
            return p.get("storage", "live"), p.get("archive")
    return "live", None


# --- Snapshot-Schreiben -----------------------------------------------------

def write_point(point_type, summary, files):
    """files: Liste {rel, action}. modified/created -> Inhalt aus Disk gezippt."""
    ensure_workdir()
    pid = new_id()
    pdir = os.path.join(BACKUP_DIR, pid)
    # Kollision (gleiche Sekunde) vermeiden
    suffix = 0
    while os.path.exists(pdir):
        suffix += 1
        pid = new_id() + "_%02d" % suffix
        pdir = os.path.join(BACKUP_DIR, pid)
    os.makedirs(pdir, exist_ok=True)

    zpath = os.path.join(pdir, "files.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            if f["action"] in ("modified", "created"):
                ap = to_abs(f["rel"])
                if not os.path.isfile(ap):
                    fail("Datei nicht gefunden: " + f["rel"])
                zf.write(ap, arcname=f["rel"])

    manifest = {
        "id": pid, "type": point_type, "summary": summary,
        "file_count": len(files), "files": files, "storage": "live",
    }
    with open(os.path.join(pdir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    idx = load_index()
    idx["points"].append({
        "id": pid, "type": point_type, "summary": summary,
        "file_count": len(files), "files": files, "storage": "live",
    })
    save_index(idx)
    return pid


# --- Archivierung (Hot/Cold-Tiering) ---------------------------------------

def point_age(p, now):
    return now - datetime.strptime(p["id"][:19], ID_FMT)


def _bundle_point(pid, arc_path):
    """Punkt-Ordner in Monats-Archiv schreiben, Lesbarkeit verifizieren.
    Rueckgabe True bei Erfolg (Ordner darf geloescht werden)."""
    pdir = os.path.join(BACKUP_DIR, pid)
    fz = os.path.join(pdir, "files.zip")
    mf = os.path.join(pdir, "manifest.json")
    if not os.path.isfile(fz):
        sys.stderr.write("WARN: files.zip fehlt fuer %s, uebersprungen\n" % pid)
        return False
    with zipfile.ZipFile(arc_path, "a", zipfile.ZIP_STORED) as az:
        names = set(az.namelist())
        if pid + "/files.zip" not in names:
            az.write(fz, arcname=pid + "/files.zip")
        if os.path.isfile(mf) and pid + "/manifest.json" not in names:
            az.write(mf, arcname=pid + "/manifest.json",
                     compress_type=zipfile.ZIP_DEFLATED)
    # Verifikation vor dem Loeschen: Eintrag muss lesbar sein.
    with zipfile.ZipFile(arc_path, "r") as az:
        az.read(pid + "/files.zip")
    return True


def archive_old(idx, now=None, force=False):
    """Hot/Cold-Tiering. Auswahl je Live-Punkt: archiviere wenn aelter als
    AGE_DAYS ODER jenseits der neuesten HOT_KEEP; neuester Punkt bleibt immer
    live. Trigger (ausser force): Live-Anzahl > COUNT_TRIGGER ODER aeltester
    Live-Punkt aelter als AGE_DAYS. Rueckgabe: Anzahl frisch archivierter."""
    if now is None:
        now = datetime.now()
    live = [p for p in sorted_points(idx) if p.get("storage", "live") == "live"]
    if not live:
        return 0
    max_age = timedelta(days=AGE_DAYS)
    age_trigger = point_age(live[0], now) > max_age
    count_trigger = len(live) > COUNT_TRIGGER
    if not force and not (age_trigger or count_trigger):
        return 0

    n = len(live)
    surplus = []
    for i, p in enumerate(live):
        rank_from_new = n - 1 - i          # 0 = neuester
        is_newest = (i == n - 1)
        archive_it = (point_age(p, now) > max_age) or (rank_from_new >= HOT_KEEP)
        if is_newest:
            archive_it = False             # Ausnahme: neuester bleibt live
        if archive_it:
            surplus.append(p)
    if not surplus:
        return 0

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    index_by_id = {p["id"]: p for p in idx["points"]}
    archived_now = 0
    for p in surplus:
        pid = p["id"]
        month = pid[:7]                    # YYYY-MM
        arc_rel = "_archive/%s.zip" % month
        arc_path = os.path.join(ARCHIVE_DIR, "%s.zip" % month)
        if not _bundle_point(pid, arc_path):
            continue
        shutil.rmtree(os.path.join(BACKUP_DIR, pid))
        index_by_id[pid]["storage"] = "archived"
        index_by_id[pid]["archive"] = arc_rel
        archived_now += 1

    if archived_now:
        recount_archived(idx)
        save_index(idx)
    return archived_now


def cmd_archive():
    n = archive_old(load_index(), force=True)
    print("Archiviert: %d Punkt(e)." % n)
    return EXIT_OK


def auto_archive():
    n = archive_old(load_index())
    if n:
        print("Archiviert: %d alte(r) Punkt(e) nach _archive/." % n)


# --- Aktion -1: Basis-Snapshot ---------------------------------------------

def cmd_baseline():
    rels = walk_project()
    if not rels:
        fail("Keine Dateien fuer Basis-Snapshot gefunden.")
    files = [{"rel": r, "action": "created"} for r in rels]
    pid = write_point("baseline", "Basis-Snapshot (Voll)", files)
    print("Basis-Snapshot erstellt: %s (%d Dateien)" % (pid, len(files)))
    auto_archive()
    return EXIT_OK


# --- Aktion -2: W-H-P aus restore_FILES.md ----------------------------------

def parse_staging():
    if not os.path.isfile(FILES_MD):
        fail("restore_FILES.md fehlt (%s)." % FILES_MD, EXIT_NO_STAGING)
    summary = None
    entries = []
    with open(FILES_MD, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("summary:"):
                summary = line.split(":", 1)[1].strip()
                continue
            parts = line.split(None, 1)
            if parts[0] in ACTIONS and len(parts) == 2:
                entries.append((parts[0], parts[1].strip()))
            else:
                entries.append((None, line))
    return summary, entries


def tracked_rels(idx):
    s = set()
    for p in idx["points"]:
        for f in p["files"]:
            s.add(f["rel"])
    return s


def resolve_action(action, rel, known):
    if action:
        return action
    ap = to_abs(rel)
    if not os.path.exists(ap):
        return "deleted"
    return "modified" if rel in known else "created"


def clear_staging(summary):
    ensure_workdir()
    header = "summary: %s\n\n" % (summary or "")
    with open(FILES_MD, "w", encoding="utf-8") as fh:
        fh.write(header)


def compute_auto_delta(idx):
    """Datei-Set per Diff Arbeitsbaum gegen letzten Punkt (autoritativ).
    Rueckgabe Liste {rel, action}. Leere Liste = nichts geaendert."""
    pts = sorted_points(idx)
    if not pts:
        fail("Kein Punkt vorhanden - erst -1 Baseline erstellen.", EXIT_ERR)
    last_point = pts[-1]
    desired = replay_to(idx, last_point)
    files = []
    for rel, source_pid in desired.items():
        if source_pid is None:
            continue
        ap = to_abs(rel)
        if not os.path.isfile(ap):
            files.append({"rel": rel, "action": "deleted"})
            continue
        old = read_from_point(idx, source_pid, rel)
        with open(ap, "rb") as fh:
            cur = fh.read()
        if cur != old:
            files.append({"rel": rel, "action": "modified"})
    for rel in walk_project():
        if rel not in desired or desired[rel] is None:
            files.append({"rel": rel, "action": "created"})
    return files


def cmd_whp(cli_summary, auto=False):
    if auto:
        idx = load_index()
        files = compute_auto_delta(idx)
        staged_summary = None
        if os.path.isfile(FILES_MD):
            staged_summary, _ = parse_staging()
        summary = (cli_summary or staged_summary
                   or "%s session auto-snapshot"
                   % datetime.now().isoformat(timespec="seconds"))
        if not files:
            clear_staging(None)
            print("Auto-Snapshot: kein Delta, kein Punkt geschrieben.")
            return EXIT_OK
        pid = write_point("whp", summary, files)
        clear_staging(None)
        print("W-H-P (auto) erstellt: %s - %s (%d Dateien)"
              % (pid, summary, len(files)))
        auto_archive()
        return EXIT_OK
    summary, entries = parse_staging()
    summary = cli_summary or summary
    if not summary:
        fail("Kein summary (weder -m noch summary:-Zeile).", EXIT_NO_STAGING)
    if not entries:
        fail("restore_FILES.md enthaelt keine Dateien.", EXIT_NO_STAGING)
    known = tracked_rels(load_index())
    files = []
    for action, rel in entries:
        files.append({"rel": rel, "action": resolve_action(action, rel, known)})
    pid = write_point("whp", summary, files)
    clear_staging(None)
    print("W-H-P erstellt: %s - %s (%d Dateien)" % (pid, summary, len(files)))
    auto_archive()
    return EXIT_OK


# --- Aktion -3: Restore (Time-Travel) --------------------------------------

def select_point(idx, selector):
    pts = sorted_points(idx)
    if not pts:
        fail("Keine Wiederherstellungspunkte vorhanden.", EXIT_NO_POINT)
    if selector == "-1":
        whps = [p for p in pts if p.get("type") == "whp"]
        if not whps:
            fail("Kein W-H-P (type=whp) vorhanden.", EXIT_NO_POINT)
        return whps[-1]
    if selector.startswith("--"):
        key = selector[2:]
        if "_" in key and len(key) > 10:  # volle ID
            for p in pts:
                if p["id"] == key:
                    return p
            fail("Kein W-H-P mit ID %s." % key, EXIT_NO_POINT)
        else:  # nur Datum -> juengster des Tages
            match = [p for p in pts if p["id"].startswith(key)]
            if not match:
                fail("Kein W-H-P am Datum %s." % key, EXIT_NO_POINT)
            return match[-1]
    fail("Ungueltiger Selektor: %s" % selector)


def replay_to(idx, target):
    """Desired state at target: rel -> source_point_id (None = geloescht)."""
    pts = sorted_points(idx)
    desired = {}
    for p in pts:
        if p["id"] > target["id"]:
            break
        for f in p["files"]:
            if f["action"] == "deleted":
                desired[f["rel"]] = None
            else:
                desired[f["rel"]] = p["id"]
    return desired


def read_from_point(idx, pid, rel):
    """Liest rel-Bytes aus Live-Ordner ODER aus Monats-Archiv (transparent)."""
    storage, archive = point_storage(idx, pid)
    if storage == "archived":
        apath = os.path.join(WORKDIR, archive.replace("/", os.sep))
        with zipfile.ZipFile(apath, "r") as az:
            inner = az.read(pid + "/files.zip")
        with zipfile.ZipFile(io.BytesIO(inner), "r") as zf:
            return zf.read(rel)
    zpath = os.path.join(BACKUP_DIR, pid, "files.zip")
    with zipfile.ZipFile(zpath, "r") as zf:
        return zf.read(rel)


def extract_from_point(idx, pid, rel, dest_abs):
    """Liest rel-Inhalt aus Live-Ordner ODER aus Monats-Archiv und schreibt
    ihn auf Disk."""
    data = read_from_point(idx, pid, rel)
    os.makedirs(os.path.dirname(dest_abs) or ".", exist_ok=True)
    with open(dest_abs, "wb") as fh:
        fh.write(data)


def apply_restore(idx, target):
    desired = replay_to(idx, target)
    all_tracked = tracked_rels(idx)
    written = deleted = 0
    for rel in sorted(all_tracked):
        ap = to_abs(rel)
        src = desired.get(rel, "ABSENT")
        if src not in ("ABSENT", None):
            extract_from_point(idx, src, rel, ap)
            written += 1
        else:
            if os.path.isfile(ap):
                os.remove(ap)
                deleted += 1
    print("Restore auf %s - %s" % (target["id"], target["summary"]))
    print("  %d Dateien geschrieben, %d geloescht" % (written, deleted))


def cmd_restore(selector):
    idx = load_index()
    if selector:
        target = select_point(idx, selector)
    else:
        target = interactive_pick(idx)
        if target is None:
            return EXIT_OK
    apply_restore(idx, target)
    return EXIT_OK


# --- Aktion --status --------------------------------------------------------

def cmd_status():
    idx = load_index()
    pts = idx["points"]
    live = sum(1 for p in pts if p.get("storage", "live") == "live")
    arch = sum(1 for p in pts if p.get("storage", "live") == "archived")
    print("Projekt:     %s" % PROJECT_NAME)
    print("Backup-Root: %s" % WORKDIR)
    print("Punkte:      %d gesamt (%d live, %d archiviert)" % (len(pts), live, arch))
    if os.path.isdir(ARCHIVE_DIR):
        for f in sorted(os.listdir(ARCHIVE_DIR)):
            ap = os.path.join(ARCHIVE_DIR, f)
            if os.path.isfile(ap):
                print("  _archive/%s (%d KB)" % (f, os.path.getsize(ap) // 1024))
    return EXIT_OK


# --- Pagination / Interaktiv ------------------------------------------------

def paginate(items, render, extra_keys=None):
    """Rueckgabe: ("item", obj) bei Ziffernwahl, ("key", taste) bei
    extra_keys-Treffer, None bei [q]."""
    extra_keys = extra_keys or {}
    page = 0
    pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE or 1
    while True:
        start = page * PAGE_SIZE
        chunk = items[start:start + PAGE_SIZE]
        print("\n(Seite %d/%d)\n" % (page + 1, pages))
        for i, it in enumerate(chunk, start=start + 1):
            print(" [%d] %s" % (i, render(it)))
        nav = " [n] naechste  [p] vorige"
        for k, label in extra_keys.items():
            nav += "  [%s] %s" % (k, label)
        nav += "  [q] abbrechen"
        print("\n" + nav)
        sel = input("Auswahl: ").strip().lower()
        if sel == "q":
            return None
        if sel in extra_keys:
            return ("key", sel)
        if sel == "n":
            page = min(page + 1, pages - 1)
            continue
        if sel == "p":
            page = max(page - 1, 0)
            continue
        if sel.isdigit():
            n = int(sel)
            if 1 <= n <= len(items):
                return ("item", items[n - 1])
        print("Ungueltig.")


def _point_label(p):
    mark = "[A] " if p.get("storage", "live") == "archived" else ""
    return "%s%s - %s" % (mark, p["id"], p["summary"])


def interactive_pick(idx):
    pts = list(reversed(sorted_points(idx)))  # juengster zuerst
    if not pts:
        fail("Keine Wiederherstellungspunkte vorhanden.", EXIT_NO_POINT)
    live = sum(1 for p in pts if p.get("storage", "live") == "live")
    arch = len(pts) - live
    print("Punkte: %d live, %d archiviert ([A] = archiviert)" % (live, arch))
    res = paginate(pts, _point_label)
    if res is None or res[0] != "item":
        return None
    chosen = res[1]
    # Schritt 2: Datei-Uebersicht mit [r] wiederherstellen im Nav.
    files = chosen["files"]
    print("\nPunkt %s - %d Dateien" % (chosen["id"], chosen["file_count"]))
    while True:
        res2 = paginate(
            files,
            lambda f: "%-9s %s" % (f["action"], f["rel"]),
            extra_keys={"r": "wiederherstellen"},
        )
        if res2 is None:
            return None
        if res2[0] == "key":  # 'r'
            return chosen
        # Ziffernwahl in Datei-Liste ohne Funktion -> erneut anzeigen.


# --- Menue ------------------------------------------------------------------

def menu():
    idx = load_index()
    live = sum(1 for p in idx["points"] if p.get("storage", "live") == "live")
    arch = idx.get("archived_count", 0)
    print("restore.py - Wiederherstellungspunkt-Tool")
    print("Punkte: %d live, %d archiviert\n" % (live, arch))
    print(" [1] Volles Backup (Basis-Snapshot) erstellen")
    print(" [2] Neuen W-H-P aus restore_FILES.md erstellen")
    print(" [3] W-H-P wiederherstellen (Time-Travel)")
    print(" [4] Alte Punkte jetzt archivieren (--archive)")
    print(" [5] Status anzeigen")
    print(" [q] abbrechen")
    sel = input("Auswahl: ").strip().lower()
    if sel == "1":
        return cmd_baseline()
    if sel == "2":
        return cmd_whp(None)
    if sel == "3":
        return cmd_restore(None)
    if sel == "4":
        return cmd_archive()
    if sel == "5":
        return cmd_status()
    return EXIT_OK


# --- Argument-Dispatch ------------------------------------------------------

def main(argv):
    migrate_legacy()
    if not argv:
        return menu()
    head = argv[0]
    if head == "-1":
        return cmd_baseline()
    if head == "-2":
        cli_summary = None
        if "-m" in argv:
            i = argv.index("-m")
            if i + 1 < len(argv):
                cli_summary = argv[i + 1]
        return cmd_whp(cli_summary, auto="--auto" in argv)
    if head == "-3":
        selector = argv[1] if len(argv) > 1 else None
        return cmd_restore(selector)
    if head == "--archive":
        return cmd_archive()
    if head == "--status":
        return cmd_status()
    fail("Unbekanntes Argument: %s" % head)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
