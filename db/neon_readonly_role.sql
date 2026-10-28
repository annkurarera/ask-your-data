-- Run once on Neon AFTER loading the data (see docs/DEPLOY.md, step 2).
-- Replace CHANGE_ME with a long random password (letters + numbers, 20+ characters).
CREATE ROLE nl2sql_reader LOGIN PASSWORD 'CHANGE_ME';
GRANT CONNECT ON DATABASE neondb TO nl2sql_reader;
GRANT USAGE ON SCHEMA public TO nl2sql_reader;
GRANT SELECT ON loan_portfolio TO nl2sql_reader;
ALTER ROLE nl2sql_reader SET default_transaction_read_only = on;
ALTER ROLE nl2sql_reader SET statement_timeout = '15s';
ALTER ROLE nl2sql_reader CONNECTION LIMIT 20;
