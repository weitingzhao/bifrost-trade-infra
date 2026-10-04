-- TD-74: read-only dry-run for dropping settings.flex_default_range_days / flex_init_range_days
-- (bifrost_dev / stg / prod). Run with default_transaction_read_only=on. Changes nothing, and
-- reads cleanly after the drop too (a column already gone shows present = false and is skipped).
SELECT t.column_name,
       c.data_type, c.is_nullable, c.column_default,
       c.column_name IS NOT NULL AS present
FROM (VALUES ('flex_default_range_days'), ('flex_init_range_days')) AS t(column_name)
LEFT JOIN information_schema.columns c
  ON c.table_schema = 'public' AND c.table_name = 'settings' AND c.column_name = t.column_name
ORDER BY 1;

-- The values (exported to ~/bifrost-backups before the commit; 2026-10-04: 30 / 270 in all three).
SELECT
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
          AND table_name = 'settings' AND column_name = 'flex_default_range_days') AS has_default,
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
          AND table_name = 'settings' AND column_name = 'flex_init_range_days') AS has_init
\gset
\if :has_default
SELECT id, flex_default_range_days FROM public.settings ORDER BY id;
\endif
\if :has_init
SELECT id, flex_init_range_days FROM public.settings ORDER BY id;
\endif
SELECT count(*) AS settings_rows FROM public.settings;

-- Anything that depends on the two columns (views, rules, indexes, constraints): must be 0 rows.
-- A column default is the column's own (pg_attrdef) and goes with it.
SELECT d.classid::regclass AS kind, d.objid, a.attname AS column_name
FROM pg_attribute a
JOIN pg_depend d ON d.refobjid = a.attrelid AND d.refobjsubid = a.attnum
WHERE a.attrelid = 'public.settings'::regclass
  AND a.attname IN ('flex_default_range_days', 'flex_init_range_days')
  AND d.deptype <> 'i'
  AND d.classid <> 'pg_attrdef'::regclass;

-- Column-level grants on them (TD-85 grants are table-level): must be 0 rows.
SELECT attname, attacl FROM pg_attribute
WHERE attrelid = 'public.settings'::regclass
  AND attname IN ('flex_default_range_days', 'flex_init_range_days')
  AND attacl IS NOT NULL;

-- Who owns the table (the commit runs as postgres; bifrost owns it).
SELECT pg_get_userbyid(relowner) AS settings_owner FROM pg_class WHERE oid = 'public.settings'::regclass;
