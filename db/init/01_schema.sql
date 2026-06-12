-- BHB DB-Schema (Blueprint 6). Idempotent für Re-Init.

CREATE TABLE IF NOT EXISTS projects (
    id           TEXT PRIMARY KEY,         -- org/repo
    bughunty_yml JSONB NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  TEXT REFERENCES projects(id),
    commit_hash TEXT NOT NULL,
    repro_class CHAR(1) CHECK (repro_class IN ('A','B','C')),
    tone_tag    TEXT,                       -- neutral|urgent|emotional
    repro_hash  TEXT,                       -- Dedup
    repro_yml   JSONB,                      -- Reporter-Playbook
    status      TEXT DEFAULT 'submitted',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS verdicts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id   UUID REFERENCES reports(id) UNIQUE,
    verdict     TEXT CHECK (verdict IN ('V1','V2','V3','REJECTED')),
    severity    TEXT,                       -- P0..P4
    audit_ref   TEXT,                       -- minio-Pfad
    detail      JSONB,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS certificates (
    id          TEXT PRIMARY KEY,           -- BHB-2024-001
    verdict_id  UUID REFERENCES verdicts(id),
    commit_hash TEXT,
    env_hash    TEXT,
    signature   TEXT NOT NULL,              -- Ed25519
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reporters (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    handle      TEXT UNIQUE,
    trust_level INT DEFAULT 0,
    v1_count    INT DEFAULT 0
);
