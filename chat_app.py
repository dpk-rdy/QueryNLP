"""
Chat Web App — A beautiful chat interface for the NL-to-SQL engine.

Provides a FastAPI backend with a chat-like web frontend where users can
type natural language questions and get SQL, results, and charts back.
"""

import os
import json
import base64
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from db_manager import DatabaseManager
from nl_engine import NLEngine
from chart_generator import generate_chart as create_chart, CHART_COLORS, CHART_BORDER_COLORS

app = FastAPI(title="QueryNLP")

# Shared state
db = DatabaseManager()
engine: NLEngine | None = None

# Auto-connect to sample DB on startup
SAMPLE_DB = os.path.join(os.path.dirname(__file__), "sample_data", "sample.db")


# Ensure upload directory exists
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@app.on_event("startup")
async def startup():
    global engine
    if os.path.exists(SAMPLE_DB):
        db.connect("sqlite", SAMPLE_DB)
    try:
        engine = NLEngine()
    except ValueError:
        print("⚠️  OPENAI_API_KEY not set. Set it to enable NL-to-SQL.")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the chat UI."""
    html_path = os.path.join(os.path.dirname(__file__), "chat_ui.html")
    with open(html_path, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/schema")
async def get_schema():
    """Return the current database schema."""
    if not db.connection:
        return JSONResponse({"error": "No database connected"}, status_code=400)
    return {
        "schema": db.schema,
        "description": db.get_schema_description(),
        "db_type": db.db_type,
    }


@app.post("/api/connect")
async def connect_database(request: Request):
    """Connect to a database."""
    body = await request.json()
    db_type = body.get("db_type", "sqlite")
    connection_string = body.get("connection_string", "")
    try:
        db.connect(db_type, connection_string)
        table_count = len(db.schema)
        total_rows = sum(t["row_count"] for t in db.schema.values())
        return {
            "success": True,
            "tables": table_count,
            "rows": total_rows,
            "schema": db.get_schema_description(),
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/upload")
async def upload_database(file: UploadFile = File(...)):
    """Upload a SQLite database file and connect to it."""
    if not file.filename.endswith((".db", ".sqlite")):
        return JSONResponse({"error": "Only .db or .sqlite files are allowed"}, status_code=400)

    file_path = UPLOAD_DIR / file.filename
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Connect to the uploaded database
        db.connect("sqlite", str(file_path))

        table_count = len(db.schema)
        total_rows = sum(t["row_count"] for t in db.schema.values())
        return {
            "success": True,
            "filename": file.filename,
            "tables": table_count,
            "rows": total_rows,
            "schema": db.get_schema_description(),
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ask")
async def ask_question(request: Request):
    """Process a natural language question and return SQL + results + chart config."""
    if not db.connection:
        return JSONResponse({"error": "No database connected"}, status_code=400)
    if not engine:
        return JSONResponse({"error": "OpenAI API key not configured"}, status_code=400)

    body = await request.json()
    question = body.get("question", "").strip()
    if not question:
        return JSONResponse({"error": "No question provided"}, status_code=400)

    try:
        # Generate SQL
        schema_desc = db.get_schema_description()
        sql = engine.generate_sql(schema_desc, question, db.db_type)

        # Execute query
        result = db.execute_query(sql)
        markdown_table = db.format_results_as_markdown(result)

        # Get chart suggestion
        chart_config = None
        if result["rows"] and len(result["columns"]) >= 2:
            try:
                suggestion = engine.suggest_chart_type(
                    question, result["columns"], result["rows"]
                )
                chart_config = _build_chart_config(result, suggestion)
            except Exception:
                pass  # Chart is optional

        return {
            "question": question,
            "sql": sql,
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"],
            "markdown_table": markdown_table,
            "chart_config": chart_config,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/explain")
async def explain_query(request: Request):
    """Generate SQL and explain it step by step."""
    if not db.connection:
        return JSONResponse({"error": "No database connected"}, status_code=400)
    if not engine:
        return JSONResponse({"error": "OpenAI API key not configured"}, status_code=400)

    body = await request.json()
    question = body.get("question", "").strip()
    if not question:
        return JSONResponse({"error": "No question provided"}, status_code=400)

    try:
        schema_desc = db.get_schema_description()
        sql = engine.generate_sql(schema_desc, question, db.db_type)
        explanation = engine.explain_sql(sql, schema_desc)
        return {"question": question, "sql": sql, "explanation": explanation}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _build_chart_config(result: dict, suggestion: dict) -> dict:
    """Build a Chart.js config from query results and suggestion."""
    columns = result["columns"]
    rows = result["rows"]

    x_col = suggestion.get("x_column", columns[0])
    y_cols = suggestion.get("y_columns", columns[1:2])
    chart_type = suggestion.get("chart_type", "bar")

    x_idx = columns.index(x_col) if x_col in columns else 0
    labels = [str(row[x_idx]) for row in rows]

    datasets = []
    for i, yc in enumerate(y_cols):
        y_idx = columns.index(yc) if yc in columns else (1 if len(columns) > 1 else 0)
        values = []
        for row in rows:
            try:
                values.append(float(row[y_idx]))
            except (TypeError, ValueError):
                values.append(0)

        color_idx = i % len(CHART_COLORS)
        ds = {
            "label": yc,
            "data": values,
            "backgroundColor": CHART_COLORS[color_idx] if chart_type in ("bar", "horizontalBar", "line") else CHART_COLORS[:len(values)],
            "borderColor": CHART_BORDER_COLORS[color_idx] if chart_type in ("bar", "horizontalBar", "line") else CHART_BORDER_COLORS[:len(values)],
            "borderWidth": 2,
        }
        if chart_type == "line":
            ds["fill"] = True
            ds["tension"] = 0.4
            ds["pointRadius"] = 4
        datasets.append(ds)

    chartjs_type = "bar" if chart_type == "horizontalBar" else chart_type

    config = {
        "type": chartjs_type,
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {
                    "display": len(datasets) > 1 or chart_type in ("pie", "doughnut"),
                    "labels": {"color": "#e2e8f0"},
                },
            },
        },
    }

    if chart_type not in ("pie", "doughnut"):
        config["options"]["scales"] = {
            "x": {"ticks": {"color": "#94a3b8"}, "grid": {"color": "rgba(148,163,184,0.1)"}},
            "y": {"ticks": {"color": "#94a3b8"}, "grid": {"color": "rgba(148,163,184,0.1)"}, "beginAtZero": True},
        }
    if chart_type == "horizontalBar":
        config["options"]["indexAxis"] = "y"

    return {
        "config": config,
        "title": suggestion.get("title", ""),
        "chart_type": chart_type,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
