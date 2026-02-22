"""
Database Manager — abstraction layer for connecting to and querying databases.

Supports SQLite (built-in), PostgreSQL, and MySQL. Provides schema introspection,
safe read-only query execution, and result formatting.
"""

import sqlite3
import json
from typing import Any


class DatabaseManager:
    """Manages database connections, schema introspection, and query execution."""

    def __init__(self):
        self.connection = None
        self.db_type: str | None = None
        self.schema: dict | None = None

    def connect(self, db_type: str, connection_string: str) -> dict:
        """
        Connect to a database.

        Args:
            db_type: One of 'sqlite', 'postgresql', 'mysql'
            connection_string: For sqlite, the file path. For postgres/mysql, a connection URI.

        Returns:
            Schema information dict.

        Raises:
            ValueError: If db_type is unsupported.
            ConnectionError: If connection fails.
        """
        db_type = db_type.lower().strip()
        self.db_type = db_type

        # Close existing connection if any
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass

        try:
            if db_type == "sqlite":
                self.connection = sqlite3.connect(connection_string)
                self.connection.row_factory = sqlite3.Row
            elif db_type in ("postgresql", "postgres"):
                self.db_type = "postgresql"
                try:
                    import psycopg2
                    import psycopg2.extras
                except ImportError:
                    raise ImportError(
                        "psycopg2 is required for PostgreSQL. "
                        "Install it with: pip install psycopg2-binary"
                    )
                self.connection = psycopg2.connect(connection_string)
                self.connection.set_session(readonly=True, autocommit=True)
            elif db_type == "mysql":
                try:
                    import mysql.connector
                except ImportError:
                    raise ImportError(
                        "mysql-connector-python is required for MySQL. "
                        "Install it with: pip install mysql-connector-python"
                    )
                self.connection = mysql.connector.connect(
                    **self._parse_mysql_uri(connection_string)
                )
            else:
                raise ValueError(
                    f"Unsupported database type: '{db_type}'. "
                    f"Supported: sqlite, postgresql, mysql"
                )
        except (ValueError, ImportError):
            raise
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {db_type}: {e}")

        self.schema = self._introspect_schema()
        return self.schema

    def _parse_mysql_uri(self, uri: str) -> dict:
        """Parse a MySQL connection string into connection parameters."""
        # Support format: mysql://user:pass@host:port/database
        if uri.startswith("mysql://"):
            uri = uri[8:]
        parts = {}
        if "@" in uri:
            user_pass, host_db = uri.rsplit("@", 1)
            if ":" in user_pass:
                parts["user"], parts["password"] = user_pass.split(":", 1)
            else:
                parts["user"] = user_pass
        else:
            host_db = uri

        if "/" in host_db:
            host_port, parts["database"] = host_db.rsplit("/", 1)
        else:
            host_port = host_db

        if ":" in host_port:
            parts["host"], port = host_port.split(":", 1)
            parts["port"] = int(port)
        else:
            parts["host"] = host_port

        return parts

    def _introspect_schema(self) -> dict:
        """Introspect the database schema and return structured info."""
        if self.db_type == "sqlite":
            return self._introspect_sqlite()
        elif self.db_type == "postgresql":
            return self._introspect_postgresql()
        elif self.db_type == "mysql":
            return self._introspect_mysql()
        return {}

    def _introspect_sqlite(self) -> dict:
        """Introspect SQLite database schema."""
        cursor = self.connection.cursor()
        schema = {}

        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            # Get column info
            cursor.execute(f"PRAGMA table_info('{table}')")
            columns = []
            for col in cursor.fetchall():
                columns.append({
                    "name": col[1],
                    "type": col[2],
                    "nullable": not col[3],
                    "primary_key": bool(col[5]),
                    "default": col[4],
                })

            # Get foreign keys
            cursor.execute(f"PRAGMA foreign_key_list('{table}')")
            foreign_keys = []
            for fk in cursor.fetchall():
                foreign_keys.append({
                    "column": fk[3],
                    "references_table": fk[2],
                    "references_column": fk[4],
                })

            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM '{table}'")
            row_count = cursor.fetchone()[0]

            schema[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "row_count": row_count,
            }

        return schema

    def _introspect_postgresql(self) -> dict:
        """Introspect PostgreSQL database schema."""
        cursor = self.connection.cursor()
        schema = {}

        # Get all tables in public schema
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            # Get column info
            cursor.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
            """, (table,))
            columns = []
            for col in cursor.fetchall():
                columns.append({
                    "name": col[0],
                    "type": col[1],
                    "nullable": col[2] == "YES",
                    "primary_key": False,  # Updated below
                    "default": col[3],
                })

            # Mark primary keys
            cursor.execute("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass AND i.indisprimary
            """, (table,))
            pk_cols = {row[0] for row in cursor.fetchall()}
            for col in columns:
                if col["name"] in pk_cols:
                    col["primary_key"] = True

            # Get foreign keys
            cursor.execute("""
                SELECT
                    kcu.column_name,
                    ccu.table_name AS foreign_table,
                    ccu.column_name AS foreign_column
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = %s
            """, (table,))
            foreign_keys = []
            for fk in cursor.fetchall():
                foreign_keys.append({
                    "column": fk[0],
                    "references_table": fk[1],
                    "references_column": fk[2],
                })

            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM \"{table}\"")
            row_count = cursor.fetchone()[0]

            schema[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "row_count": row_count,
            }

        return schema

    def _introspect_mysql(self) -> dict:
        """Introspect MySQL database schema."""
        cursor = self.connection.cursor()
        schema = {}

        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            cursor.execute(f"DESCRIBE `{table}`")
            columns = []
            for col in cursor.fetchall():
                columns.append({
                    "name": col[0],
                    "type": col[1],
                    "nullable": col[2] == "YES",
                    "primary_key": col[3] == "PRI",
                    "default": col[4],
                })

            # Get foreign keys
            cursor.execute(f"""
                SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE TABLE_NAME = '{table}' 
                AND REFERENCED_TABLE_NAME IS NOT NULL
                AND TABLE_SCHEMA = DATABASE()
            """)
            foreign_keys = []
            for fk in cursor.fetchall():
                foreign_keys.append({
                    "column": fk[0],
                    "references_table": fk[1],
                    "references_column": fk[2],
                })

            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            row_count = cursor.fetchone()[0]

            schema[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "row_count": row_count,
            }

        return schema

    def get_schema_description(self) -> str:
        """Return a human/LLM-readable schema description for prompt context."""
        if not self.schema:
            return "No database connected."

        lines = [f"Database Type: {self.db_type}", ""]

        for table_name, info in self.schema.items():
            lines.append(f"Table: {table_name} ({info['row_count']} rows)")
            lines.append("-" * 50)

            for col in info["columns"]:
                pk = " [PRIMARY KEY]" if col["primary_key"] else ""
                nullable = " NULL" if col["nullable"] else " NOT NULL"
                lines.append(f"  {col['name']}: {col['type']}{nullable}{pk}")

            if info["foreign_keys"]:
                lines.append("  Foreign Keys:")
                for fk in info["foreign_keys"]:
                    lines.append(
                        f"    {fk['column']} → {fk['references_table']}.{fk['references_column']}"
                    )
            lines.append("")

        return "\n".join(lines)

    def execute_query(self, sql: str, max_rows: int = 1000) -> dict:
        """
        Execute a read-only SQL query.

        Args:
            sql: The SQL query to execute.
            max_rows: Maximum number of rows to return (default 1000).

        Returns:
            Dict with 'columns' (list[str]), 'rows' (list[list]), and 'row_count' (int).

        Raises:
            ValueError: If query contains write operations.
            RuntimeError: If query execution fails.
        """
        # Safety: reject write operations
        sql_upper = sql.strip().upper()
        dangerous_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "REPLACE", "MERGE"]
        first_word = sql_upper.split()[0] if sql_upper.split() else ""
        if first_word in dangerous_keywords:
            raise ValueError(
                f"Write operations are not allowed. Detected: {first_word}. "
                f"Only SELECT queries are permitted."
            )

        try:
            cursor = self.connection.cursor()
            cursor.execute(sql)
            rows = cursor.fetchmany(max_rows)

            # Get column names
            if self.db_type == "sqlite":
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = [list(row) for row in rows]
            elif self.db_type == "postgresql":
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = [list(row) for row in rows]
            elif self.db_type == "mysql":
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = [list(row) for row in rows]
            else:
                columns = []

            total_count = len(rows)
            truncated = total_count >= max_rows

            return {
                "columns": columns,
                "rows": rows,
                "row_count": total_count,
                "truncated": truncated,
            }
        except Exception as e:
            raise RuntimeError(f"Query execution failed: {e}")

    def format_results_as_markdown(self, result: dict) -> str:
        """Format query results as a markdown table."""
        columns = result["columns"]
        rows = result["rows"]

        if not columns:
            return "Query returned no results."

        # Build markdown table
        header = "| " + " | ".join(str(c) for c in columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        body_lines = []
        for row in rows:
            body_lines.append("| " + " | ".join(str(v) for v in row) + " |")

        table = "\n".join([header, separator] + body_lines)

        if result.get("truncated"):
            table += f"\n\n*Results truncated to {result['row_count']} rows.*"

        return table

    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.db_type = None
            self.schema = None
