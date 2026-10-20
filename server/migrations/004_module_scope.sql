-- 004_module_scope.sql — assessments belong to a module, not to the platform.
-- Existing rows are all from the Strategy module.

ALTER TABLE attempts ADD COLUMN module_id TEXT;
UPDATE attempts SET module_id = 'strategy' WHERE module_id IS NULL;

ALTER TABLE practical_submissions ADD COLUMN module_id TEXT;
UPDATE practical_submissions SET module_id = 'strategy' WHERE module_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_attempts_module ON attempts(user_id, module_id, kind);
CREATE INDEX IF NOT EXISTS idx_practical_module ON practical_submissions(user_id, module_id, id);
