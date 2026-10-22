-- 002_content.sql — modules, lessons, templates, revisions and audit trail.
-- Content becomes database-backed so the admin area authors the real source of truth.

CREATE TABLE IF NOT EXISTS modules (
    id TEXT PRIMARY KEY,
    component TEXT NOT NULL,
    title TEXT NOT NULL,
    tagline TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL DEFAULT 'Foundation',
    hours TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    intro_json TEXT NOT NULL DEFAULT '[]',
    practical_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    position INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_modules_component ON modules(component, status);

CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    minutes INTEGER NOT NULL DEFAULT 10,
    summary TEXT NOT NULL DEFAULT '',
    body_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lessons_module ON lessons(module_id, position);

CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL DEFAULT 'Markdown',
    filename TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_templates_module ON templates(module_id, position);

CREATE TABLE IF NOT EXISTS content_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    editor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revisions_entity ON content_revisions(entity, entity_id, id);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity, entity_id, id);

-- Questions become discoverable per module without changing the existing rows.
ALTER TABLE questions ADD COLUMN module_id TEXT;
UPDATE questions SET module_id = 'strategy'
 WHERE component = 'strategy' AND kind IN ('quiz', 'scenario') AND module_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_questions_module ON questions(module_id, kind, active);
