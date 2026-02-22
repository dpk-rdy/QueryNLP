"""
NL-to-SQL + Visualization MCP Server

An MCP server that connects to databases, converts natural language to SQL,
executes queries, generates Chart.js visualizations, and creates dashboards.

Tools:
  - connect_db: Connect to a database and introspect its schema
  - ask_question: Ask a question in plain English, get SQL + results
  - generate_chart: Generate an interactive Chart.js visualization
  - explain_query: Get a human-readable explanation of the generated SQL
  - save_dashboard: Create a multi-chart dashboard from multiple questions
"""

import os
import json
from mcp.server.fastmcp import FastMCP
from db_manager import DatabaseManager
from nl_engine import NLEngine
from chart_generator import generate_chart as create_chart, generate_dashboard, CHART_COLORS, CHART_BORDER_COLORS

# ─── Server Setup ────────────────────────────────────────────────────────────

mcp = FastMCP(
    "QueryNLP",
    instructions=(
        "Connect to any database, ask questions in plain English, "
        "get SQL + results, generate charts, and build dashboards."
    ),
)

# Shared state
db_manager = DatabaseManager()
nl_engine: NLEngine | None = None


def _get_engine() -> NLEngine:
    """Get or initialize the NL engine."""
    global nl_engine
    if nl_engine is None:
        nl_engine = NLEngine()
    return nl_engine


# ─── Tool: connect_db ────────────────────────────────────────────────────────

@mcp.tool()
def connect_db(db_type: str, connection_string: str) -> str:
    """
    Connect to a database and introspect its schema.

    Args:
        db_type: Database type — one of 'sqlite', 'postgresql', 'mysql'.
        connection_string: For SQLite, the file path (e.g., './sample_data/sample.db').
                          For PostgreSQL, a connection URI (e.g., 'postgresql://user:pass@host:5432/db').
                          For MySQL, a connection URI (e.g., 'mysql://user:pass@host:3306/db').

    Returns:
        A summary of the database schema including tables, columns, types, and relationships.
    """
    try:
        db_manager.connect(db_type, connection_string)
        schema_desc = db_manager.get_schema_description()

        table_count = len(db_manager.schema)
        total_rows = sum(t["row_count"] for t in db_manager.schema.values())

        return (
            f"✅ Connected to {db_type} database successfully!\n\n"
            f"📊 **{table_count} tables** found with **{total_rows:,} total rows**\n\n"
            f"**Schema:**\n\n{schema_desc}"
        )
    except Exception as e:
        return f"❌ Connection failed: {e}"


# ─── Tool: ask_question ─────────────────────────────────────────────────────

@mcp.tool()
def ask_question(question: str) -> str:
    """
    Ask a question about your data in plain English and get SQL + results.

    The question is converted to SQL using AI, executed safely (read-only),
    and results are returned as a formatted markdown table.

    Args:
        question: A natural language question about the data.
                  Examples:
                  - "What's the average salary by department?"
                  - "Show me the top 10 products by total sales"
                  - "How many employees were hired each year?"
                  - "Which region has the highest revenue?"

    Returns:
        The generated SQL query and formatted results.
    """
    if not db_manager.connection:
        return "❌ No database connected. Use `connect_db` first."

    try:
        engine = _get_engine()
        schema_desc = db_manager.get_schema_description()

        # Generate SQL
        sql = engine.generate_sql(schema_desc, question, db_manager.db_type)

        # Execute query
        result = db_manager.execute_query(sql)
        formatted = db_manager.format_results_as_markdown(result)

        return (
            f"**Question:** {question}\n\n"
            f"**Generated SQL:**\n```sql\n{sql}\n```\n\n"
            f"**Results** ({result['row_count']} rows):\n\n{formatted}"
        )
    except Exception as e:
        return f"❌ Error: {e}"


# ─── Tool: generate_chart ───────────────────────────────────────────────────

@mcp.tool()
def generate_chart(question: str, chart_type: str = "") -> str:
    """
    Generate an interactive Chart.js visualization from a natural language question.

    Converts the question to SQL, executes it, then generates a self-contained
    HTML file with an interactive chart. Automatically selects the best chart type
    if not specified.

    Args:
        question: A natural language question about the data.
        chart_type: Optional chart type override. One of: bar, line, pie, doughnut,
                    scatter, horizontalBar. If empty, the best type is auto-selected.

    Returns:
        The file path to the generated HTML chart and a summary.
    """
    if not db_manager.connection:
        return "❌ No database connected. Use `connect_db` first."

    try:
        engine = _get_engine()
        schema_desc = db_manager.get_schema_description()

        # Generate and execute SQL
        sql = engine.generate_sql(schema_desc, question, db_manager.db_type)
        result = db_manager.execute_query(sql)

        if not result["rows"]:
            return "❌ Query returned no data to chart."

        # Determine chart type
        if chart_type:
            suggestion = {
                "chart_type": chart_type,
                "x_column": result["columns"][0],
                "y_columns": result["columns"][1:2] if len(result["columns"]) > 1 else result["columns"][:1],
                "title": question,
            }
        else:
            suggestion = engine.suggest_chart_type(
                question, result["columns"], result["rows"]
            )

        # Generate chart
        output_dir = os.path.join(os.path.dirname(__file__), "charts")
        filepath = create_chart(
            data=result,
            chart_type=suggestion["chart_type"],
            x_column=suggestion["x_column"],
            y_columns=suggestion["y_columns"],
            title=suggestion.get("title", question),
            output_dir=output_dir,
        )

        return (
            f"📊 Chart generated successfully!\n\n"
            f"**Question:** {question}\n"
            f"**Chart Type:** {suggestion['chart_type']}\n"
            f"**SQL:**\n```sql\n{sql}\n```\n"
            f"**File:** `{filepath}`\n\n"
            f"Open this HTML file in a browser to view the interactive chart."
        )
    except Exception as e:
        return f"❌ Error generating chart: {e}"


# ─── Tool: explain_query ────────────────────────────────────────────────────

@mcp.tool()
def explain_query(question: str) -> str:
    """
    Generate the SQL for a question and provide a step-by-step explanation.

    This tool does NOT execute the query — it only generates the SQL and explains
    what each part does in plain English. Useful for learning SQL or reviewing
    the query before execution.

    Args:
        question: A natural language question about the data.

    Returns:
        The generated SQL and a detailed step-by-step explanation.
    """
    if not db_manager.connection:
        return "❌ No database connected. Use `connect_db` first."

    try:
        engine = _get_engine()
        schema_desc = db_manager.get_schema_description()

        # Generate SQL
        sql = engine.generate_sql(schema_desc, question, db_manager.db_type)

        # Explain it
        explanation = engine.explain_sql(sql, schema_desc)

        return (
            f"**Question:** {question}\n\n"
            f"**Generated SQL:**\n```sql\n{sql}\n```\n\n"
            f"**Explanation:**\n\n{explanation}"
        )
    except Exception as e:
        return f"❌ Error: {e}"


# ─── Tool: save_dashboard ───────────────────────────────────────────────────

@mcp.tool()
def save_dashboard(name: str, questions: list[str]) -> str:
    """
    Create a multi-chart dashboard from a list of natural language questions.

    Each question is converted to SQL, executed, and visualized as a chart.
    All charts are combined into a single responsive HTML dashboard page.

    Args:
        name: Dashboard name (e.g., "Sales Overview", "HR Analytics").
        questions: A list of natural language questions. Each becomes a chart.
                   Example: ["Total sales by region", "Monthly revenue trend",
                            "Top 5 products by quantity sold"]

    Returns:
        The file path to the generated dashboard HTML and a summary.
    """
    if not db_manager.connection:
        return "❌ No database connected. Use `connect_db` first."

    try:
        engine = _get_engine()
        schema_desc = db_manager.get_schema_description()

        charts = []
        errors = []

        for i, question in enumerate(questions):
            try:
                # Generate and execute SQL
                sql = engine.generate_sql(schema_desc, question, db_manager.db_type)
                result = db_manager.execute_query(sql)

                if not result["rows"]:
                    errors.append(f"  - Q{i+1}: No data returned")
                    continue

                # Get chart suggestion
                suggestion = engine.suggest_chart_type(
                    question, result["columns"], result["rows"]
                )

                # Build Chart.js config
                columns = result["columns"]
                rows = result["rows"]

                x_col = suggestion.get("x_column", columns[0])
                y_cols = suggestion.get("y_columns", columns[1:2])

                x_idx = columns.index(x_col) if x_col in columns else 0
                labels = [str(row[x_idx]) for row in rows]

                datasets = []
                for j, yc in enumerate(y_cols):
                    y_idx = columns.index(yc) if yc in columns else (1 if len(columns) > 1 else 0)
                    values = []
                    for row in rows:
                        try:
                            values.append(float(row[y_idx]))
                        except (TypeError, ValueError):
                            values.append(0)

                    color_idx = j % len(CHART_COLORS)
                    ds = {
                        "label": yc,
                        "data": values,
                        "backgroundColor": CHART_COLORS[color_idx],
                        "borderColor": CHART_BORDER_COLORS[color_idx],
                        "borderWidth": 2,
                    }
                    if suggestion["chart_type"] == "line":
                        ds["fill"] = True
                        ds["tension"] = 0.4
                    datasets.append(ds)

                chart_type = suggestion["chart_type"]
                config = {
                    "type": "bar" if chart_type == "horizontalBar" else chart_type,
                    "data": {"labels": labels, "datasets": datasets},
                    "options": {
                        "responsive": True,
                        "maintainAspectRatio": False,
                        "plugins": {
                            "legend": {
                                "display": len(datasets) > 1 or chart_type in ("pie", "doughnut"),
                            },
                        },
                    },
                }

                if chart_type not in ("pie", "doughnut"):
                    config["options"]["scales"] = {
                        "x": {"display": True},
                        "y": {"display": True, "beginAtZero": True},
                    }
                if chart_type == "horizontalBar":
                    config["options"]["indexAxis"] = "y"

                charts.append({
                    "title": suggestion.get("title", question),
                    "config": config,
                })

            except Exception as e:
                errors.append(f"  - Q{i+1} ({question}): {e}")

        if not charts:
            return f"❌ No charts could be generated.\n\nErrors:\n" + "\n".join(errors)

        # Generate dashboard
        output_dir = os.path.join(os.path.dirname(__file__), "dashboards")
        filepath = generate_dashboard(charts, name, output_dir)

        result_msg = (
            f"📊 Dashboard **\"{name}\"** created successfully!\n\n"
            f"**Charts:** {len(charts)} of {len(questions)} questions visualized\n"
            f"**File:** `{filepath}`\n\n"
            f"Open this HTML file in a browser to view the interactive dashboard."
        )

        if errors:
            result_msg += f"\n\n**Warnings:**\n" + "\n".join(errors)

        return result_msg

    except Exception as e:
        return f"❌ Error creating dashboard: {e}"


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
