#!/bin/bash
# 02_load_data.sh: loads data/loan_portfolio.csv (mounted at /data) and builds indexes.
# Runs automatically the first time the Postgres container starts.
set -e

CSV=/data/loan_portfolio.csv
if [ ! -f "$CSV" ]; then
  echo "ERROR: $CSV not found. Put loan_portfolio.csv in the data/ folder (see README step 3)." >&2
  exit 1
fi

echo "Loading $CSV ... (about 1 minute for 10 lakh rows)"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-EOSQL
  COPY loan_portfolio FROM '$CSV' WITH (FORMAT csv, HEADER true, NULL '');
  CREATE INDEX idx_lp_product   ON loan_portfolio (product_type);
  CREATE INDEX idx_lp_status    ON loan_portfolio (loan_status);
  CREATE INDEX idx_lp_disb_date ON loan_portfolio (disbursement_date);
  CREATE INDEX idx_lp_branch    ON loan_portfolio (branch_code);
  CREATE INDEX idx_lp_state     ON loan_portfolio (state);
  CREATE INDEX idx_lp_customer  ON loan_portfolio (customer_id);
  ANALYZE loan_portfolio;
EOSQL
echo "Loaded: $(psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT COUNT(*) FROM loan_portfolio') rows"
