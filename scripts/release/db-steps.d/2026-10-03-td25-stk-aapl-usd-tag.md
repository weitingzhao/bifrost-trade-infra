---
id: 2026-10-03-td25-stk-aapl-usd-tag
envs: dev stg prod
when: before
done:
---
# TD-25: delete the one position-category tag keyed 'STK-AAPL-USD'

`preference_position_category_tags` has one row per env keyed `STK-AAPL-USD` (category_id 2, 2026-05-24).
No code writes that format any more and it never matches a position (a stock position is keyed
`AAPL|STK|||`), so it tags nothing; no `AAPL|STK|||` tag exists beside it (read 2026-10-03). The plan put the
deletion to the Owner (REQUEST-td-ddl-batch-plans-2026-10-03.md, TD-25 item 2). **Not reversible** except
from the export: run the dry-run first (it writes the row to `~/bifrost-backups/trade-<env>/`), then the
commit, which refuses unless exactly 1 row goes. The alternative -- re-key it to `AAPL|STK|||` so AAPL reads
as category 2 -- would change what the Positions page shows, so it is not done here. Independent of the deliver.

Commands run from the `bifrost-trade-infra` checkout with `KUBECONFIG=~/.kube/bifrost-k3s.yaml`.

## dev
dry-run: mkdir -p ~/bifrost-backups/trade-dev && kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -q -c "SET default_transaction_read_only=on;" -c "COPY (SELECT account_id, contract_key, category_id, created_at FROM preference_position_category_tags WHERE contract_key = 'STK-AAPL-USD') TO STDOUT WITH (FORMAT csv, HEADER)" > ~/bifrost-backups/trade-dev/2026-10-03_stk-aapl-usd-tag.csv && cat ~/bifrost-backups/trade-dev/2026-10-03_stk-aapl-usd-tag.csv
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td25-stk-aapl-usd-delete.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -At -c "SET default_transaction_read_only=on;" -c "SELECT count(*) FROM preference_position_category_tags WHERE contract_key = 'STK-AAPL-USD'"   (expect 0)
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -c "COPY preference_position_category_tags (account_id, contract_key, category_id, created_at) FROM STDIN WITH (FORMAT csv, HEADER)" < ~/bifrost-backups/trade-dev/2026-10-03_stk-aapl-usd-tag.csv

## stg
dry-run: mkdir -p ~/bifrost-backups/trade-stg && kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -q -c "SET default_transaction_read_only=on;" -c "COPY (SELECT account_id, contract_key, category_id, created_at FROM preference_position_category_tags WHERE contract_key = 'STK-AAPL-USD') TO STDOUT WITH (FORMAT csv, HEADER)" > ~/bifrost-backups/trade-stg/2026-10-03_stk-aapl-usd-tag.csv && cat ~/bifrost-backups/trade-stg/2026-10-03_stk-aapl-usd-tag.csv
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td25-stk-aapl-usd-delete.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -At -c "SET default_transaction_read_only=on;" -c "SELECT count(*) FROM preference_position_category_tags WHERE contract_key = 'STK-AAPL-USD'"   (expect 0)
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -c "COPY preference_position_category_tags (account_id, contract_key, category_id, created_at) FROM STDIN WITH (FORMAT csv, HEADER)" < ~/bifrost-backups/trade-stg/2026-10-03_stk-aapl-usd-tag.csv

## prod
dry-run: mkdir -p ~/bifrost-backups/trade-prod && kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -q -c "SET default_transaction_read_only=on;" -c "COPY (SELECT account_id, contract_key, category_id, created_at FROM preference_position_category_tags WHERE contract_key = 'STK-AAPL-USD') TO STDOUT WITH (FORMAT csv, HEADER)" > ~/bifrost-backups/trade-prod/2026-10-03_stk-aapl-usd-tag.csv && cat ~/bifrost-backups/trade-prod/2026-10-03_stk-aapl-usd-tag.csv
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td25-stk-aapl-usd-delete.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -At -c "SET default_transaction_read_only=on;" -c "SELECT count(*) FROM preference_position_category_tags WHERE contract_key = 'STK-AAPL-USD'"   (expect 0)
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -c "COPY preference_position_category_tags (account_id, contract_key, category_id, created_at) FROM STDIN WITH (FORMAT csv, HEADER)" < ~/bifrost-backups/trade-prod/2026-10-03_stk-aapl-usd-tag.csv
