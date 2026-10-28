#!/bin/bash
# 03_readonly_role.sh: creates the read-only role the app connects with.
# Even if the LLM produced a DELETE and every app-level check failed,
# this role has no permission to change anything.
set -e

READER_PASSWORD="${READER_PASSWORD:-reader_pw}"

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-EOSQL
  CREATE ROLE nl2sql_reader LOGIN PASSWORD '${READER_PASSWORD}';
  REVOKE ALL ON SCHEMA public FROM PUBLIC;
  GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO nl2sql_reader;
  GRANT USAGE ON SCHEMA public TO nl2sql_reader;
  GRANT SELECT ON loan_portfolio TO nl2sql_reader;
  ALTER ROLE nl2sql_reader SET default_transaction_read_only = on;
  ALTER ROLE nl2sql_reader SET statement_timeout = '15s';
  ALTER ROLE nl2sql_reader CONNECTION LIMIT 20;
EOSQL
echo "Created read-only role nl2sql_reader"
