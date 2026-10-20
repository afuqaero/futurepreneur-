-- 003_checkup.sql — expand the business profile for Check-Up v2.
-- Optional at the API level so existing clients keep working; the UI asks for it.

ALTER TABLE profiles ADD COLUMN customer_type TEXT NOT NULL DEFAULT '';
