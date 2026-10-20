-- Rename the platform and any template downloads created under the old name.
UPDATE settings SET value = 'futurePreneur' WHERE key = 'platform_name' AND value <> 'futurePreneur';

UPDATE templates
SET filename = 'futurepreneur-' || substr(filename, 10)
WHERE filename LIKE 'bizready-%';
