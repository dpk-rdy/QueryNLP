# ⚡ QueryNLP — MCP Server & Data Interface

[![MCP](https://img.shields.io/badge/MCP-Protocol-blue.svg)](https://modelcontextprotocol.io/)
[![OpenAI](https://img.shields.io/badge/AI-GPT--4o-orange.svg)](https://openai.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An advanced Model Context Protocol (MCP) server paired with **QueryNLP** - a web interface for natural language data exploration. Connect to your database, ask questions in plain English, and get SQL, results, and interactive Chart.js visualizations instantly.

---

## ✨ Key Features

- **🗣️ Natural Language to SQL:** Ask complex questions ("Who are our top 10 customers by revenue this month?") and get precise SQL.
- **📊 Interactive Visualizations:** Automatically generates Chart.js charts (Bar, Line, Pie, etc.) based on your data.
- **📁 Multi-DB Support:** Seamlessly connect to **SQLite**, **PostgreSQL**, and **MySQL**.
- **🧩 MCP Integration:** Compatible with any MCP client like **Claude Desktop**, **Cursor**, or **Zed**.
- **🔍 SQL Explainer:** Get step-by-step human logins breakdowns of generated queries.
- **📅 Dynamic Dashboards:** Bundle multiple queries into a single, responsive HTML dashboard.
- **🚀 QueryNLP UI:** A sleek, dark-themed responsive web interface with a real-time schema browser.

---

## 🚀 Quick Start

### 1. Installation
Ensure you have **Python 3.10+** installed.

```bash
# Clone and enter directory
git clone https://github.com/youruser/nl-to-sql-mcp.git
cd nl-to-sql-mcp

# Setup virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration
Copy the example environment file and add your OpenAI API Key.

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

### 3. Initialize Sample Data (Optional)
```bash
python sample_data/create_sample_db.py
```

---

## 💬 Using QueryNLP (Web UI)

The web interface provides a rich, interactive experience with schema introspection and inline charting.

```bash
python chat_app.py
```
Visit **[http://127.0.0.1:8765](http://127.0.0.1:8765)**.

**Pro-tip:** Prefix questions with `/explain` to see how the SQL was constructed.

---

## 🤖 Using as an MCP Server

Integrate the AI data engine directly into your favorite AI development tools.

```bash
# Start the server
python server.py
```

### Example Client Config (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "nl-to-sql": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["/absolute/path/to/server.py"],
      "env": { "OPENAI_API_KEY": "your-key-here" }
    }
  }
}
```

---

## 🛠️ MCP Tools

| Tool | Action |
|---|---|
| `connect_db` | Connect to an existing database & map schema |
| `ask_question` | NL → SQL → Table Results |
| `generate_chart` | NL → SQL → Interactive Chart.js File |
| `explain_query` | Detailed breakdown of SQL logic |
| `save_dashboard` | Combine multiple visual insights into one dashboard |

---

## 📂 Project Structure

- `chat_app.py`: FastAPI backend for QueryNLP.
- `chat_ui.html`: Premium Frontend (Single Page).
- `server.py`: MCP Server entry point.
- `nl_engine.py`: GPT-4o powered SQL logic.
- `db_manager.py`: Database abstraction layer.
- `chart_generator.py`: Chart.js & Dashboard engine.

---

## 🛡️ Security & Safety
QueryNLP is designed for **READ-ONLY** operations. The engine is hard-coded to only generate `SELECT` statements, and the database manager enforces read-only connections where supported.

---

## 📄 License
Distributed under the MIT License. See `LICENSE` for more information.

