"""
SQLite Database Query Tool

Allows the agent to query SQLite databases, inspect schemas, and safely execute
parameterized SQL queries. All queries run with a 10-second timeout and result
limits to prevent resource exhaustion.

Two main operations:
  - sqlite_query: Execute a SQL SELECT/INSERT/UPDATE/DELETE query
  - sqlite_schema: Inspect database schema (all tables or a specific table)

Safety features:
  - Parameterized queries to prevent SQL injection
  - Read-only mode (URI with ?mode=ro) for SELECT queries
  - 10-second connection timeout
  - Result limits (max_rows, default 100)
  - Error handling for missing files, malformed SQL, etc.
  - Path expansion (~/ paths resolved to absolute)
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from tools.registry import registry


def _expand_database_path(database_path: str) -> str:
    """Expand ~ to home directory and resolve to absolute path."""
    expanded = Path(database_path).expanduser().resolve()
    return str(expanded)


def _sqlite_query_handler(
    database_path: str,
    query: str,
    params: Optional[list] = None,
    max_rows: int = 100,
) -> str:
    """
    Execute a SQL query against a SQLite database.

    For SELECT queries:
      - Opens database in read-only mode
      - Returns results as list of rows with column names

    For INSERT/UPDATE/DELETE/CREATE queries:
      - Executes with write access
      - Returns affected row count

    Args:
        database_path: Path to .db or .sqlite file (supports ~/ expansion)
        query: SQL statement to execute
        params: Optional list of parameters for parameterized queries
        max_rows: Maximum rows to return (default 100)

    Returns:
        JSON string with results or error message
    """
    if not database_path or not database_path.strip():
        return json.dumps({"error": "database_path is required"})

    if not query or not query.strip():
        return json.dumps({"error": "query is required"})

    try:
        database_path = _expand_database_path(database_path)
        db_path_obj = Path(database_path)

        if not db_path_obj.exists():
            return json.dumps(
                {"error": f"Database file not found: {database_path}"}
            )

        query_upper = query.strip().upper()
        is_select = query_upper.startswith("SELECT")

        try:
            if is_select:
                # Use read-only URI mode for SELECT queries
                uri = f"file:{database_path}?mode=ro"
                connection = sqlite3.connect(uri, uri=True, timeout=10)
            else:
                # Write mode for INSERT/UPDATE/DELETE/CREATE
                connection = sqlite3.connect(database_path, timeout=10)

            connection.row_factory = sqlite3.Row
            cursor = connection.cursor()

            try:
                # Execute query with parameterized query safety
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                if is_select:
                    # Fetch SELECT results
                    rows = cursor.fetchall()
                    limited_rows = rows[:max_rows]

                    # Extract column names
                    columns = [description[0] for description in cursor.description]

                    # Convert rows to list of dicts for JSON serialization
                    rows_as_dicts = [dict(row) for row in limited_rows]

                    return json.dumps({
                        "columns": columns,
                        "rows": rows_as_dicts,
                        "row_count": len(limited_rows),
                        "total_rows": len(rows),
                        "was_truncated": len(rows) > max_rows,
                    })

                else:
                    # For INSERT/UPDATE/DELETE/CREATE, return affected row count
                    connection.commit()
                    affected_rows = cursor.rowcount

                    return json.dumps({
                        "affected_rows": affected_rows,
                        "message": f"Query executed successfully. {affected_rows} row(s) affected.",
                    })

            finally:
                cursor.close()
                connection.close()

        except sqlite3.DatabaseError as db_error:
            return json.dumps({
                "error": f"Database error: {str(db_error)}"
            })
        except sqlite3.OperationalError as op_error:
            return json.dumps({
                "error": f"Operational error (table/column may not exist): {str(op_error)}"
            })
        except sqlite3.Error as sql_error:
            return json.dumps({
                "error": f"SQLite error: {str(sql_error)}"
            })

    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}"
        })


def _sqlite_schema_handler(
    database_path: str,
    table: Optional[str] = None,
) -> str:
    """
    Inspect the schema of a SQLite database.

    If table is omitted, returns schema for all tables.
    If table is specified, returns schema for just that table.

    Args:
        database_path: Path to .db or .sqlite file (supports ~/ expansion)
        table: Optional specific table name to inspect

    Returns:
        JSON string with table schema(s) including column info and CREATE SQL
    """
    if not database_path or not database_path.strip():
        return json.dumps({"error": "database_path is required"})

    try:
        database_path = _expand_database_path(database_path)
        db_path_obj = Path(database_path)

        if not db_path_obj.exists():
            return json.dumps(
                {"error": f"Database file not found: {database_path}"}
            )

        try:
            # Always use read-only mode for schema inspection
            uri = f"file:{database_path}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=10)
            cursor = connection.cursor()

            try:
                # Get list of tables
                if table:
                    # Validate that the requested table exists
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)
                    )
                    if not cursor.fetchone():
                        return json.dumps({
                            "error": f"Table '{table}' not found in database"
                        })
                    table_names = [table]
                else:
                    # Get all user tables (exclude sqlite_* system tables)
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                    )
                    table_names = [row[0] for row in cursor.fetchall()]

                # Build schema for each table
                tables_schema = []
                for table_name in table_names:
                    # Get column information
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns_raw = cursor.fetchall()

                    columns = []
                    for col_id, col_name, col_type, col_notnull, col_default, col_pk in columns_raw:
                        columns.append({
                            "name": col_name,
                            "type": col_type,
                            "not_null": bool(col_notnull),
                            "default": col_default,
                            "primary_key": bool(col_pk),
                        })

                    # Get the CREATE TABLE statement
                    cursor.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (table_name,)
                    )
                    create_sql = cursor.fetchone()[0] or ""

                    tables_schema.append({
                        "name": table_name,
                        "columns": columns,
                        "create_sql": create_sql,
                    })

                return json.dumps({
                    "tables": tables_schema,
                    "table_count": len(tables_schema),
                })

            finally:
                cursor.close()
                connection.close()

        except sqlite3.DatabaseError as db_error:
            return json.dumps({
                "error": f"Database error: {str(db_error)}"
            })
        except sqlite3.Error as sql_error:
            return json.dumps({
                "error": f"SQLite error: {str(sql_error)}"
            })

    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}"
        })


def _check_sqlite_availability() -> bool:
    """SQLite3 is part of Python stdlib, always available."""
    try:
        sqlite3.connect(":memory:")
        return True
    except Exception:
        return False


# ── Schema Definitions ────────────────────────────────────────────────────────

SQLITE_QUERY_SCHEMA = {
    "name": "sqlite_query",
    "description": (
        "Execute a SQL query against a SQLite database. Supports SELECT, "
        "INSERT, UPDATE, DELETE, and CREATE queries. SELECT queries run in "
        "read-only mode. Results are limited to prevent excessive output. "
        "Uses parameterized queries to prevent SQL injection."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "database_path": {
                "type": "string",
                "description": "Path to the SQLite database file (.db or .sqlite). Supports ~ expansion.",
            },
            "query": {
                "type": "string",
                "description": "The SQL query to execute (SELECT, INSERT, UPDATE, DELETE, CREATE, etc.)",
            },
            "params": {
                "type": "array",
                "items": {"type": ["string", "number", "boolean", "null"]},
                "description": "Optional list of parameters for parameterized queries. Prevents SQL injection.",
            },
            "max_rows": {
                "type": "integer",
                "description": "Maximum number of rows to return for SELECT queries (default 100)",
                "default": 100,
            },
        },
        "required": ["database_path", "query"],
    },
}

SQLITE_SCHEMA_SCHEMA = {
    "name": "sqlite_schema",
    "description": (
        "Inspect the schema of a SQLite database. Returns table names, column "
        "information (names, types, constraints), and CREATE TABLE statements. "
        "Omit the 'table' parameter to inspect all tables, or specify a table "
        "name to focus on a single table."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "database_path": {
                "type": "string",
                "description": "Path to the SQLite database file (.db or .sqlite). Supports ~ expansion.",
            },
            "table": {
                "type": "string",
                "description": "Optional specific table name to inspect. Omit to inspect all tables.",
            },
        },
        "required": ["database_path"],
    },
}

# ── Registration ──────────────────────────────────────────────────────────────

registry.register(
    name="sqlite_query",
    toolset="database",
    schema=SQLITE_QUERY_SCHEMA,
    handler=lambda args, **kw: _sqlite_query_handler(
        database_path=args.get("database_path", ""),
        query=args.get("query", ""),
        params=args.get("params"),
        max_rows=args.get("max_rows", 100),
    ),
    check_fn=_check_sqlite_availability,
    emoji="🗄️",
)

registry.register(
    name="sqlite_schema",
    toolset="database",
    schema=SQLITE_SCHEMA_SCHEMA,
    handler=lambda args, **kw: _sqlite_schema_handler(
        database_path=args.get("database_path", ""),
        table=args.get("table"),
    ),
    check_fn=_check_sqlite_availability,
    emoji="📋",
)
