import pytest

from app.validator import SQLValidationError, validate_sql

T = {"loan_portfolio"}

ALLOWED = [
    "SELECT COUNT(*) FROM loan_portfolio",
    "select region, sum(outstanding_principal) from loan_portfolio group by 1",
    "SELECT * FROM public.loan_portfolio LIMIT 5",
    "WITH m AS (SELECT DATE_TRUNC('month', disbursement_date) AS m FROM loan_portfolio) SELECT m, COUNT(*) FROM m GROUP BY 1",
    "SELECT product_type FROM loan_portfolio UNION SELECT channel FROM loan_portfolio",
    "SELECT COUNT(*) FILTER (WHERE loan_status = 'NPA') FROM loan_portfolio",
    "SELECT branch_code, RANK() OVER (ORDER BY SUM(dpd) DESC) FROM loan_portfolio GROUP BY branch_code",
    "SELECT disbursement_date + make_interval(months => tenure_months) FROM loan_portfolio",
    "SELECT EXTRACT(YEAR FROM disbursement_date + INTERVAL '9 months') AS fy FROM loan_portfolio",
    "SELECT * FROM (SELECT city FROM loan_portfolio) AS sub",
    "SELECT COUNT(*) FROM loan_portfolio;",  # trailing semicolon is fine
]

BLOCKED = [
    ("DROP TABLE loan_portfolio", "Only SELECT"),
    ("DELETE FROM loan_portfolio WHERE loan_status = 'Closed'", "Only SELECT"),
    ("UPDATE loan_portfolio SET dpd = 0", "Only SELECT"),
    ("INSERT INTO loan_portfolio (loan_id) VALUES ('x')", "Only SELECT"),
    ("TRUNCATE loan_portfolio", "Only SELECT"),
    ("CREATE TABLE loans_copy AS SELECT * FROM loan_portfolio", "Only SELECT"),
    ("ALTER TABLE loan_portfolio ADD COLUMN x int", "Only SELECT"),
    ("GRANT ALL ON loan_portfolio TO public", "Only SELECT"),
    ("COPY loan_portfolio TO '/tmp/out.csv'", "Only SELECT"),
    ("SET statement_timeout = 0", "Only SELECT"),
    ("SELECT 1 FROM loan_portfolio; DROP TABLE loan_portfolio", "Exactly one"),
    ("SELECT * INTO loans_copy FROM loan_portfolio", "INTO"),
    ("WITH d AS (DELETE FROM loan_portfolio RETURNING *) SELECT * FROM d", "DELETE"),
    ("SELECT * FROM loan_portfolio FOR UPDATE", "LOCK"),
    ("SELECT pg_sleep(30)", "pg_sleep"),
    ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT current_setting('data_directory')", "current_setting"),
    ("SELECT version()", "Function not allowed"),
    ("SELECT current_user", "Function not allowed"),
    ("SELECT * FROM pg_catalog.pg_tables", "System tables"),
    ("SELECT * FROM pg_user", "System tables"),
    ("SELECT table_name FROM information_schema.tables", "System tables"),
    ("SELECT * FROM salaries", "Unknown table"),
    ("SELECT * FROM loan_portfolio JOIN employees USING (customer_id)", "Unknown table"),
    ("SELECT * FROM other_schema.loan_portfolio", "Schema not allowed"),
    ("SELECT * FROM generate_series(1, 1000000000)", "Table functions"),
    ("", "Empty"),
    ("this is not sql", ""),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed_queries_pass(sql):
    assert validate_sql(sql, T).sql


@pytest.mark.parametrize("sql,reason", BLOCKED)
def test_dangerous_queries_blocked(sql, reason):
    with pytest.raises(SQLValidationError) as e:
        validate_sql(sql, T)
    assert reason in str(e.value)


def test_limit_added_when_missing():
    v = validate_sql("SELECT * FROM loan_portfolio", T, max_rows=1000)
    assert v.limit_applied and v.sql.rstrip().endswith("LIMIT 1000")


def test_large_limit_capped():
    v = validate_sql("SELECT * FROM loan_portfolio LIMIT 50000", T, max_rows=1000)
    assert "LIMIT 1000" in v.sql and "50000" not in v.sql


def test_small_limit_kept():
    v = validate_sql("SELECT * FROM loan_portfolio ORDER BY dpd DESC LIMIT 10", T, max_rows=1000)
    assert not v.limit_applied and "LIMIT 10" in v.sql


def test_union_is_wrapped_with_limit():
    v = validate_sql("SELECT city FROM loan_portfolio UNION SELECT state FROM loan_portfolio", T, max_rows=50)
    assert v.sql.rstrip().endswith("LIMIT 50")


def test_table_name_case_insensitive():
    assert validate_sql("SELECT COUNT(*) FROM LOAN_PORTFOLIO", T).sql


def test_count_sql_when_cap_applied():
    v = validate_sql("SELECT loan_id FROM loan_portfolio WHERE dpd > 0", T, max_rows=1000)
    assert v.count_sql.startswith("SELECT COUNT(*) AS total_rows FROM (")
    assert "LIMIT" not in v.count_sql


def test_no_count_sql_when_user_limit_is_small():
    assert validate_sql("SELECT loan_id FROM loan_portfolio LIMIT 10", T).count_sql is None


@pytest.mark.parametrize("sql", [
    "SELECT SUM(disbursed_amount) FROM loan_portfolio",
    "SELECT COUNT(*) AS loans, ROUND(AVG(interest_rate), 2) FROM loan_portfolio WHERE product_type = 'Home Loan'",
    "SELECT ROUND(SUM(disbursed_amount) / 1e7, 2) AS crore FROM loan_portfolio",
])
def test_single_row_aggregates_get_no_limit(sql):
    """Regression: 'LIMIT 1000' on a SUM made the summary say only 1,000 records were analysed."""
    v = validate_sql(sql, T)
    assert "LIMIT" not in v.sql and not v.limit_applied and v.count_sql is None


@pytest.mark.parametrize("sql", [
    "SELECT product_type, SUM(disbursed_amount) FROM loan_portfolio GROUP BY 1",
    "SELECT loan_id, SUM(disbursed_amount) OVER () FROM loan_portfolio",
    "SELECT loan_id, disbursed_amount FROM loan_portfolio",
    "SELECT SUM(disbursed_amount), loan_id FROM loan_portfolio",
])
def test_multi_row_queries_still_get_limit(sql):
    assert "LIMIT 1000" in validate_sql(sql, T).sql
