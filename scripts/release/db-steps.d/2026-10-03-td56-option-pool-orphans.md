---
id: 2026-10-03-td56-option-pool-orphans
envs: dev stg prod
when: after
done: dev stg prod
---
# TD-56: delete the 3 orphan 'Option Pool' symbol-order rows

`preference_market_streams_symbol_order` keeps a category's symbol order under the category's name. Three rows
per env (NVDA, TSLA, GOOG, written 2026-04-23) sit under `Option Pool`, which no category is called. Owner
approved deleting them (2026-10-03). **Not reversible** except from the export: run the dry-run first -- it
writes the rows to `~/bifrost-backups/trade-<env>/` -- then the commit, which refuses unless exactly 3 rows go
and refuses if a category named Option Pool exists by then. From core 0.41.0 a category rename / delete carries
its order rows, so no new orphans appear. Independent of the deliver (no code depends on it), so it is listed after the run (`when: after`); the dry-run exports were taken 2026-10-03 before batch c.

Commands run from the `bifrost-trade-infra` checkout with `KUBECONFIG=~/.kube/bifrost-k3s.yaml`.

## dev
dry-run: mkdir -p ~/bifrost-backups/trade-dev && kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -q -c "SET default_transaction_read_only=on;" -c "COPY (SELECT category_name, symbol, sort_order, updated_at FROM preference_market_streams_symbol_order WHERE category_name = 'Option Pool' ORDER BY sort_order) TO STDOUT WITH (FORMAT csv, HEADER)" > ~/bifrost-backups/trade-dev/2026-10-03_option-pool-symbol-order.csv && cat ~/bifrost-backups/trade-dev/2026-10-03_option-pool-symbol-order.csv
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td56-option-pool-delete.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -At -c "SET default_transaction_read_only=on;" -c "SELECT count(*) FROM preference_market_streams_symbol_order WHERE category_name = 'Option Pool'"   (expect 0)
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -v ON_ERROR_STOP=1 -c "COPY preference_market_streams_symbol_order (category_name, symbol, sort_order, updated_at) FROM STDIN WITH (FORMAT csv, HEADER)" < ~/bifrost-backups/trade-dev/2026-10-03_option-pool-symbol-order.csv

## stg
dry-run: mkdir -p ~/bifrost-backups/trade-stg && kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -q -c "SET default_transaction_read_only=on;" -c "COPY (SELECT category_name, symbol, sort_order, updated_at FROM preference_market_streams_symbol_order WHERE category_name = 'Option Pool' ORDER BY sort_order) TO STDOUT WITH (FORMAT csv, HEADER)" > ~/bifrost-backups/trade-stg/2026-10-03_option-pool-symbol-order.csv && cat ~/bifrost-backups/trade-stg/2026-10-03_option-pool-symbol-order.csv
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td56-option-pool-delete.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -At -c "SET default_transaction_read_only=on;" -c "SELECT count(*) FROM preference_market_streams_symbol_order WHERE category_name = 'Option Pool'"   (expect 0)
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_stg -X -v ON_ERROR_STOP=1 -c "COPY preference_market_streams_symbol_order (category_name, symbol, sort_order, updated_at) FROM STDIN WITH (FORMAT csv, HEADER)" < ~/bifrost-backups/trade-stg/2026-10-03_option-pool-symbol-order.csv

## prod
dry-run: mkdir -p ~/bifrost-backups/trade-prod && kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -q -c "SET default_transaction_read_only=on;" -c "COPY (SELECT category_name, symbol, sort_order, updated_at FROM preference_market_streams_symbol_order WHERE category_name = 'Option Pool' ORDER BY sort_order) TO STDOUT WITH (FORMAT csv, HEADER)" > ~/bifrost-backups/trade-prod/2026-10-03_option-pool-symbol-order.csv && cat ~/bifrost-backups/trade-prod/2026-10-03_option-pool-symbol-order.csv
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -1 -f - < scripts/release/db-steps.d/sql/2026-10-03-td56-option-pool-delete.sql
verify:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -At -c "SET default_transaction_read_only=on;" -c "SELECT count(*) FROM preference_market_streams_symbol_order WHERE category_name = 'Option Pool'"   (expect 0)
rollback: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -v ON_ERROR_STOP=1 -c "COPY preference_market_streams_symbol_order (category_name, symbol, sort_order, updated_at) FROM STDIN WITH (FORMAT csv, HEADER)" < ~/bifrost-backups/trade-prod/2026-10-03_option-pool-symbol-order.csv
