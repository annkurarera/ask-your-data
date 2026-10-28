"""SQL guardrail. Every query the LLM writes passes through here before it touches
the database. Layer 1 of defence in depth (layer 2 = read-only DB role,
layer 3 = read-only transaction + statement timeout in executor.py)."""
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

DIALECT = "postgres"

# Statement types that change data, schema or session state
_FORBIDDEN_NODES = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Drop", "Create", "Alter", "AlterTable", "Merge",
        "TruncateTable", "Command", "Copy", "Into", "Lock", "Set", "Grant", "Revoke",
        "Transaction", "Commit", "Rollback", "Use", "Pragma", "LoadData",
    )
    if hasattr(exp, name)
)

# Functions that can read files, sleep, touch other databases or change settings
_FORBIDDEN_FUNC_PREFIXES = ("pg_", "lo_", "dblink", "current_setting", "set_config",
                            "query_to_xml", "query_to_json", "txid_", "inet_server")
_FORBIDDEN_FUNC_NAMES = {"version", "current_version", "current_user", "session_user", "current_database", "inet_client_addr"}
_FORBIDDEN_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}


class SQLValidationError(ValueError):
    """Raised when generated SQL is not allowed to run."""


@dataclass
class ValidatedSQL:
    sql: str
    limit_applied: bool
    count_sql: str | None = None  # counts all matching rows when the row cap was applied


def _func_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return node.sql_name().lower()


def _single_row_aggregate(stmt: exp.Expression) -> bool:
    """True for queries like SELECT SUM(x), COUNT(*) FROM t WHERE ...: exactly one row, so no LIMIT is needed.
    (Adding one anyway made the summary model think only 1,000 records were included.)"""
    if not isinstance(stmt, exp.Select) or stmt.args.get("group") or not stmt.expressions:
        return False
    for e in stmt.expressions:
        if e.find(exp.Window) or not e.find(exp.AggFunc):
            return False
    return True


def validate_sql(sql: str, allowed_tables: set[str], max_rows: int = 1000) -> ValidatedSQL:
    if not sql or not sql.strip():
        raise SQLValidationError("Empty SQL")

    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except ParseError as e:
        raise SQLValidationError(f"SQL could not be parsed: {str(e).splitlines()[0]}") from e

    if len(statements) != 1:
        raise SQLValidationError("Exactly one SQL statement is allowed")
    stmt = statements[0]

    if not isinstance(stmt, exp.Query):
        raise SQLValidationError(f"Only SELECT queries are allowed (got {stmt.key.upper()})")

    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SQLValidationError(f"Forbidden operation: {node.key.upper()}")

    for func in stmt.find_all(exp.Func):
        name = _func_name(func)
        if name.startswith(_FORBIDDEN_FUNC_PREFIXES) or name in _FORBIDDEN_FUNC_NAMES:
            raise SQLValidationError(f"Function not allowed: {name}")

    cte_names = {cte.alias.lower() for cte in stmt.find_all(exp.CTE) if cte.alias}
    allowed = {t.lower() for t in allowed_tables}
    for table in stmt.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise SQLValidationError("Table functions are not allowed")
        schema = (table.db or "").lower()
        name = table.name.lower()
        if schema in _FORBIDDEN_SCHEMAS or name.startswith("pg_"):
            raise SQLValidationError(f"System tables are not allowed: {table.sql(dialect=DIALECT)}")
        if schema and schema != "public":
            raise SQLValidationError(f"Schema not allowed: {schema}")
        if name not in allowed and name not in cte_names:
            raise SQLValidationError(
                f"Unknown table '{table.name}'. Only these tables exist: {', '.join(sorted(allowed))}"
            )

    # Cap the number of rows returned (not needed when the query can only return one row)
    if _single_row_aggregate(stmt):
        return ValidatedSQL(sql=stmt.sql(dialect=DIALECT, pretty=True), limit_applied=False)

    limit_applied = False
    limit_node = stmt.args.get("limit")
    current = None
    if limit_node is not None:
        expr = limit_node.expression
        if isinstance(expr, exp.Literal) and expr.is_int:
            current = int(expr.this)
    count_sql = None
    if limit_node is None or current is None or current > max_rows:
        limit_applied = True
        count_sql = f"SELECT COUNT(*) AS total_rows FROM (\n{stmt.sql(dialect=DIALECT)}\n) AS q"
        if isinstance(stmt, exp.Select):
            stmt = stmt.limit(max_rows, copy=True)
            final_sql = stmt.sql(dialect=DIALECT, pretty=True)
        else:  # UNION / INTERSECT / EXCEPT: wrap it
            inner = stmt.sql(dialect=DIALECT, pretty=True)
            final_sql = f"SELECT * FROM (\n{inner}\n) AS q\nLIMIT {max_rows}"
    else:
        final_sql = stmt.sql(dialect=DIALECT, pretty=True)

    return ValidatedSQL(sql=final_sql, limit_applied=limit_applied, count_sql=count_sql)
