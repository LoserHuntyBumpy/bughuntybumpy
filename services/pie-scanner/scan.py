#!/usr/bin/env python3
# BugHuntyBumpy - Crowdsourced Bug-Bounty-Reporting-Gateway mit deterministischer Verifikation
# Copyright (C) 2026  Nope-im-not-pro  <nope-im-not-pro@keemail.me>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""BHB Layer-1 PIE Scanner - deterministische, regelbasierte Repo-Analyse.

KEINE KI. Statisch, offline (ausser optionalem git clone). Erzeugt aus einem
GitHub-Repo (oder lokalem Pfad) eine projektspezifische `bughunty.yml`, die
Layer-1-pie-web in ein adaptives Formular rendert.

Aufruf:
    scan.py <org/repo | https://github.com/org/repo[.git] | /pfad/zum/repo> \
            [--out /spec/bughunty.yml]

Module (Blueprint 3.1):
    StackProfiler  - Sprache, Framework, Runtime
    SurfaceMapper  - Entrypoints: HTTP-Routes, CLI-Args, ENV
    DependencyMiner- Manifest-Dependencies (Basis fuer CVE-Abgleich)
    TestEnvDetector- Dockerfile, Compose, pytest, jest, CI
    SASTCluster    - Hotspots via Regex (eval, subprocess, SQL, upload, auth)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML fehlt. pip install pyyaml\n")
    sys.exit(2)


# ---------------------------------------------------------------- helpers
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             "dist", "build", "vendor", ".idea", ".mypy_cache", "target"}
MAX_FILE_BYTES = 2_000_000


def iter_files(root):
    for dpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            yield os.path.join(dpath, f)


def read_text(path):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return ""
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


# ---------------------------------------------------------------- modules
LANG_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascript", ".tsx": "typescript", ".go": "go",
    ".rs": "rust", ".rb": "ruby", ".php": "php", ".java": "java",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp",
}

FRAMEWORK_MARKERS = {
    "flask": [r"from\s+flask\s+import", r"Flask\(__name__\)"],
    "django": [r"django", r"INSTALLED_APPS"],
    "fastapi": [r"from\s+fastapi\s+import", r"FastAPI\("],
    "express": [r"require\(['\"]express['\"]\)", r"from\s+['\"]express['\"]"],
    "nestjs": [r"@nestjs/"],
    "gin": [r"gin-gonic/gin"],
    "spring": [r"org\.springframework"],
    "rails": [r"Rails\.application"],
}

DB_MARKERS = {
    "postgres": [r"psycopg", r"pg\b", r"postgresql://"],
    "mysql": [r"mysql", r"pymysql"],
    "sqlite": [r"sqlite3", r"sqlite://"],
    "mongodb": [r"pymongo", r"mongoose"],
    "redis": [r"redis"],
}

# Bug-Klassen-Relevanz pro Stack -> filtert irrelevante Optionen im Formular.
SAST_RULES = {
    "rce": [r"\beval\s*\(", r"\bexec\s*\(", r"subprocess\.(run|call|Popen)",
            r"os\.system", r"child_process", r"\bvm\.runIn"],
    "sqli": [r"execute\(\s*[\"'].*%s", r"\+\s*req\.(query|body|params)",
             r"SELECT\s+.*\+\s*", r"f[\"']SELECT", r"raw\(\s*[\"`]"],
    "lfi": [r"open\(\s*.*request", r"send_file\(", r"sendFile\(",
            r"path\.join\(.*req\.", r"fs\.readFile\(.*req\."],
    "xss": [r"render_template_string", r"dangerouslySetInnerHTML",
            r"\.innerHTML\s*=", r"v-html"],
    "upload": [r"request\.files", r"multer", r"FileUpload", r"MultipartFile"],
    "auth": [r"auth", r"login", r"jwt", r"session", r"passport", r"middleware"],
}


def scan_repo(root):
    langs, frameworks, dbs = {}, set(), set()
    entrypoints = {"http": set(), "cli": set(), "env": set()}
    testenv = {"docker": False, "compose": False, "make_test": False,
               "pytest": False, "jest": False, "ci": False}
    deps = {}
    hotspots = {k: [] for k in SAST_RULES}

    route_re = re.compile(
        r"@app\.(route|get|post|put|delete)|app\.(get|post|put|delete|use)\s*\("
        r"|router\.(get|post|put|delete)|http\.HandleFunc")
    cli_re = re.compile(r"argparse|click\.command|cobra\.Command|process\.argv"
                        r"|sys\.argv|flag\.(String|Int|Bool)")
    env_re = re.compile(r"os\.environ|os\.getenv|process\.env\.(\w+)"
                        r"|getenv\(")

    for path in iter_files(root):
        base = os.path.basename(path).lower()
        ext = os.path.splitext(path)[1].lower()
        r = rel(root, path)

        if ext in LANG_EXT:
            langs[LANG_EXT[ext]] = langs.get(LANG_EXT[ext], 0) + 1

        # TestEnv-Marker per Dateiname
        if base in ("dockerfile",) or base.startswith("dockerfile"):
            testenv["docker"] = True
        if base in ("docker-compose.yml", "docker-compose.yaml",
                    "compose.yml", "compose.yaml"):
            testenv["compose"] = True
        if base == "makefile":
            if re.search(r"^test:", read_text(path), re.M):
                testenv["make_test"] = True
        if base in ("pytest.ini", "tox.ini", "conftest.py"):
            testenv["pytest"] = True
        if base in ("jest.config.js", "jest.config.ts"):
            testenv["jest"] = True
        if ".github/workflows" in r or base in (".gitlab-ci.yml",):
            testenv["ci"] = True

        # Dependency-Manifeste
        if base == "requirements.txt":
            for line in read_text(path).splitlines():
                n = re.split(r"[=<>!~ ]", line.strip(), 1)[0]
                if n and not n.startswith("#"):
                    deps.setdefault("pypi", set()).add(n)
        if base == "package.json":
            txt = read_text(path)
            for n in re.findall(r'"([^"]+)"\s*:\s*"[^"]*"',
                                _section(txt, "dependencies")):
                deps.setdefault("npm", set()).add(n)
        if base == "go.mod":
            for n in re.findall(r"^\s+([\w./-]+)\s+v", read_text(path), re.M):
                deps.setdefault("go", set()).add(n)

        # Inhaltsbasierte Marker nur fuer Code
        if ext not in LANG_EXT and base not in ("requirements.txt",):
            continue
        txt = read_text(path)
        if not txt:
            continue

        for fw, pats in FRAMEWORK_MARKERS.items():
            if any(re.search(p, txt) for p in pats):
                frameworks.add(fw)
        for db, pats in DB_MARKERS.items():
            if any(re.search(p, txt) for p in pats):
                dbs.add(db)

        if route_re.search(txt):
            entrypoints["http"].add(r)
        if cli_re.search(txt):
            entrypoints["cli"].add(r)
        for m in env_re.findall(txt):
            entrypoints["env"].add(r)

        for klass, pats in SAST_RULES.items():
            for p in pats:
                if re.search(p, txt) and len(hotspots[klass]) < 20:
                    hotspots[klass].append(r)
                    break

    return {
        "languages": langs,
        "frameworks": sorted(frameworks),
        "databases": sorted(dbs),
        "entrypoints": {k: sorted(v) for k, v in entrypoints.items()},
        "testenv": testenv,
        "dependencies": {k: sorted(v) for k, v in deps.items()},
        "hotspots": {k: v for k, v in hotspots.items() if v},
    }


def _section(json_txt, key):
    try:
        data = json.loads(json_txt)
    except (ValueError, TypeError):
        return ""
    sub = data.get(key)
    return json.dumps(sub) if isinstance(sub, dict) else ""


# ---------------------------------------------------------------- yml gen
def build_bughunty_yml(project_id, commit, facts):
    has_db = bool(facts["databases"])
    runtime = []
    if facts["testenv"]["docker"] or facts["testenv"]["compose"]:
        runtime.append("docker")
    if "python" in facts["languages"]:
        runtime.append("venv")
    if "javascript" in facts["languages"] or "typescript" in facts["languages"]:
        runtime.append("nvm")
    runtime = runtime or ["docker"]

    # Tier-1 nur Bug-Klassen, deren Hotspots existieren (kein SQLi ohne DB).
    t1_all = ["xss", "sqli", "rce", "lfi", "crash", "dos_resource"]
    present = set(facts["hotspots"]) | {"crash", "dos_resource"}
    if not has_db:
        present.discard("sqli")
    tier1 = [k for k in t1_all if k in present]

    # Reproduzierbarkeits-Default: A wenn Container/Build vorhanden.
    repro_default = "A" if (facts["testenv"]["docker"]
                            or facts["testenv"]["compose"]) else "B"

    # Proof-of-Context aus realen Entrypoints (maschinell pruefbar gegen AST).
    poc = []
    for f in facts["entrypoints"]["http"][:1]:
        poc.append({
            "q": "In welcher Datei ist ein HTTP-Handler dieses Projekts "
                 "deklariert?",
            "answer_source": "ast",
            "hint_files": [f],
        })
    for klass, files in list(facts["hotspots"].items())[:2]:
        if klass == "auth":
            continue
        poc.append({
            "q": "Nenne die Datei, in der die gemeldete %s-relevante "
                 "Code-Stelle liegt." % klass,
            "answer_source": "ast",
            "hint_files": files[:3],
        })

    spec = {
        "project_id": project_id,
        "commit_default": commit,
        "detected": {
            "languages": facts["languages"],
            "frameworks": facts["frameworks"],
            "databases": facts["databases"],
            "entrypoint_counts": {k: len(v)
                                  for k, v in facts["entrypoints"].items()},
            "testenv": facts["testenv"],
        },
        "required_environment": {
            "runtime": runtime,
            "proof_fields": _proof_fields(facts),
        },
        "reproducibility_default": repro_default,
        "proof_of_context": poc,
        "tiers": {
            "tier1_deterministic": tier1,
            "tier2_stochastic": ["race_condition", "logic_state_bug"],
            "tier3_manual": ["feature_request", "ui_ux", "performance"],
        },
        "scanner": {
            "version": "1.0",
            "deterministic": True,
            "facts_hash": hashlib.sha256(
                repr(sorted(facts["hotspots"].items())).encode()
            ).hexdigest()[:16],
        },
    }
    return spec


def _proof_fields(facts):
    fields = []
    if facts["entrypoints"]["http"]:
        fields.append({"type": "http_request",
                       "required_headers": True, "body_schema": "json"})
    if facts["entrypoints"]["cli"]:
        fields.append({"type": "cli_invocation"})
    fields.append({"type": "terminal_log"})
    return fields


# ---------------------------------------------------------------- main
def resolve_source(src):
    """Lokaler Pfad -> direkt. org/repo oder URL -> shallow clone in tmp."""
    if os.path.isdir(src):
        commit = _git_head(src)
        return src, commit, None
    if re.match(r"^[\w.-]+/[\w.-]+$", src):
        url = "https://github.com/%s.git" % src
        pid = src
    else:
        url = src if src.endswith(".git") else src + ".git"
        m = re.search(r"github\.com[:/]+([\w.-]+/[\w.-]+?)(?:\.git)?$", src)
        pid = m.group(1) if m else "unknown/repo"
    tmp = tempfile.mkdtemp(prefix="bhb-scan-")
    subprocess.run(
        ["git", "clone", "--depth", "1", url, tmp],
        check=True, capture_output=True, text=True, timeout=120
    )
    return tmp, _git_head(tmp), pid


def _git_head(path):
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True)
        return r.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def main():
    ap = argparse.ArgumentParser(description="BHB PIE Repo-Scanner")
    ap.add_argument("source", help="org/repo | github-url | lokaler Pfad")
    ap.add_argument("--out", default="bughunty.yml")
    ap.add_argument("--project-id", default=None)
    args = ap.parse_args()

    root, commit, pid = resolve_source(args.source)
    project_id = args.project_id or pid or os.path.basename(
        os.path.abspath(root))
    facts = scan_repo(root)
    spec = build_bughunty_yml(project_id, commit, facts)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        yaml.safe_dump(spec, fh, sort_keys=False, allow_unicode=True)

    sys.stderr.write(
        "scan ok: %s commit=%s langs=%s tier1=%s -> %s\n" % (
            project_id, commit[:8], list(facts["languages"]),
            spec["tiers"]["tier1_deterministic"], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
