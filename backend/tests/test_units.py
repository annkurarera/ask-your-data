"""Unit tests for charts, result comparison, JSON parsing and the semantic layer."""
import pytest

from app.charts import pick_chart
from app.llm import parse_json_reply
from app.result_compare import results_match
from app.semantic import allowed_tables, load_semantic_layer, schema_context
from app.validator import validate_sql


# ---------- charts ----------
def test_kpi_for_single_number():
    assert pick_chart(["loan_book"], [[123.4]])["type"] == "kpi"


def test_line_for_time_series():
    c = pick_chart(["month", "disbursed"], [["2026-01-01", 1], ["2026-02-01", 2], ["2026-03-01", 3]])
    assert c == {"type": "line", "x": "month", "y": ["disbursed"]}


def test_year_numbers_treated_as_time():
    c = pick_chart(["year", "avg_rate"], [[2021, 8.8], [2022, 9.3], [2023, 9.6]])
    assert c["type"] == "line" and c["x"] == "year"


def test_monthly_income_count_is_a_number_not_time():
    c = pick_chart(["customers_with_monthly_income_less_than_1lakh"], [[352358]])
    assert c == {"type": "kpi", "y": ["customers_with_monthly_income_less_than_1lakh"]}


def test_month_number_column_is_time():
    c = pick_chart(["month", "loans"], [[1, 10], [2, 12], [3, 15]])
    assert c["type"] == "line" and c["x"] == "month"


def test_bar_for_category_breakdown():
    c = pick_chart(["product_type", "gross_npa_pct"], [["Home Loan", 0.7], ["Personal Loan", 4.0]])
    assert c == {"type": "bar", "x": "product_type", "y": ["gross_npa_pct"]}


def test_table_for_row_level_lists():
    rows = [["LN1", "Home Loan", 10], ["LN2", "Auto Loan", 5]]
    assert pick_chart(["loan_id", "product_type", "dpd"], rows)["type"] == "table"


def test_table_for_too_many_categories():
    rows = [[f"BR{i}", i] for i in range(100)]
    assert pick_chart(["branch_code", "loans"], rows)["type"] == "table"


def test_empty_result_is_table():
    assert pick_chart(["a"], [])["type"] == "table"


# ---------- result comparison ----------
def test_match_ignores_order_names_and_extra_columns():
    gold = (["product", "n"], [["A", 1], ["B", 2]])
    pred = (["count_loans", "product_type", "extra"], [[2, "B", "x"], [1, "A", "y"]])
    assert results_match(*gold, *pred)[0]


def test_match_tolerates_rounding():
    assert results_match(["pct"], [[1.33]], ["gnpa"], [[1.3312]])[0]


def test_mismatch_on_wrong_values():
    ok, why = results_match(["n"], [[10]], ["n"], [[11]])
    assert not ok and "no column" in why


def test_mismatch_on_row_count():
    assert not results_match(["n"], [[1], [2]], ["n"], [[1]])[0]


def test_rows_must_pair_correctly():
    gold = (["p", "n"], [["A", 1], ["B", 2]])
    pred = (["p", "n"], [["A", 2], ["B", 1]])  # same columns, wrong pairing
    assert not results_match(*gold, *pred)[0]


def test_match_columns_ignores_label_wording():
    gold = (["band", "pct"], [["<600", 13.0], ["800+", 0.1]])
    pred = (["cibil_band", "npa"], [["Below 600", 13.0], ["800 and above", 0.1]])
    assert not results_match(*gold, *pred)[0]
    assert results_match(*gold, *pred, match_columns=["pct"])[0]


# ---------- JSON parsing ----------
@pytest.mark.parametrize("text", [
    '{"action": "sql", "sql": "SELECT 1"}',
    '```json\n{"action": "sql", "sql": "SELECT 1"}\n```',
    'Here you go: {"action": "sql", "sql": "SELECT 1"} hope it helps',
    "```sql\nSELECT 1\n```",
])
def test_parse_json_reply_variants(text):
    assert parse_json_reply(text)["sql"] == "SELECT 1"


def test_parse_json_reply_garbage():
    with pytest.raises(ValueError):
        parse_json_reply("I don't know")


# ---------- semantic layer ----------
def test_schema_context_mentions_every_column():
    layer = load_semantic_layer()
    ctx = schema_context(layer)
    for col in layer["columns"]:
        assert f"- {col} (" in ctx


def test_semantic_examples_pass_validator():
    layer = load_semantic_layer()
    for ex in layer["examples"]:
        assert validate_sql(ex["sql"], allowed_tables(layer)).sql
