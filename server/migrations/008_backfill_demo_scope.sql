-- 008_backfill_demo_scope.sql — demo rows created before module-scoped
-- assessments must belong to the Strategy module, otherwise the demo learner
-- appears to have no verified module on Postgres (where the seed runs after
-- migrations).

UPDATE attempts SET module_id = 'strategy' WHERE module_id IS NULL;
UPDATE practical_submissions SET module_id = 'strategy' WHERE module_id IS NULL;
