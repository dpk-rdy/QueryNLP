"""
NL-to-SQL Engine — converts natural language questions to SQL using OpenAI GPT-4o.

Also provides SQL explanation and chart type suggestion capabilities.
"""

import json
import os
from openai import OpenAI


class NLEngine:
    """Natural language to SQL conversion engine powered by OpenAI."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set the OPENAI_API_KEY environment variable "
                "or pass it directly."
            )
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o"

    def generate_sql(self, schema_description: str, question: str, db_type: str = "sqlite") -> str:
        """
        Convert a natural language question to SQL.

        Args:
            schema_description: Human-readable schema description.
            question: Natural language question.
            db_type: Database dialect (sqlite, postgresql, mysql).

        Returns:
            SQL query string.
        """
        system_prompt = f"""You are an expert SQL query generator. Your job is to convert natural language questions into precise, efficient SQL queries.

DATABASE SCHEMA:
{schema_description}

RULES:
1. Generate ONLY a SELECT query — never INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or TRUNCATE.
2. Use the correct SQL dialect for {db_type}.
3. Always use proper table and column names from the schema.
4. Use JOINs when the question requires data from multiple tables.
5. Use appropriate aggregation functions (COUNT, SUM, AVG, MIN, MAX) when needed.
6. Add ORDER BY clauses when the question implies ranking or sorting.
7. Add LIMIT when the question asks for "top N" or similar.
8. Use aliases for readability.
9. Handle date operations using the correct dialect functions.
10. Return ONLY the raw SQL query with no markdown formatting, no explanation, no backticks — just the SQL."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=1000,
        )

        sql = response.choices[0].message.content.strip()

        # Clean up any accidental markdown formatting
        if sql.startswith("```"):
            sql = sql.split("\n", 1)[1] if "\n" in sql else sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        sql = sql.strip()

        return sql

    def explain_sql(self, sql: str, schema_description: str) -> str:
        """
        Generate a human-readable explanation of a SQL query.

        Args:
            sql: The SQL query to explain.
            schema_description: Schema context for accurate explanation.

        Returns:
            Step-by-step explanation string.
        """
        system_prompt = f"""You are an expert SQL educator. Explain the given SQL query in plain English, step by step.

DATABASE SCHEMA:
{schema_description}

RULES:
1. Break down the query into logical steps.
2. Explain what each clause does (SELECT, FROM, JOIN, WHERE, GROUP BY, ORDER BY, LIMIT, etc.).
3. Describe the expected output — what columns and what kind of data the user will see.
4. If there are JOINs, explain why those tables are being connected.
5. If there are aggregations, explain what they compute.
6. Keep the explanation clear and concise, suitable for someone learning SQL.
7. Format the response in markdown with numbered steps."""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Explain this SQL query:\n\n{sql}"},
            ],
            temperature=0.3,
            max_tokens=1500,
        )

        return response.choices[0].message.content.strip()

    def suggest_chart_type(
        self, question: str, columns: list[str], sample_data: list[list]
    ) -> dict:
        """
        Suggest the best chart type and configuration for the given data.

        Args:
            question: Original natural language question.
            columns: Column names from the query result.
            sample_data: First few rows of data.

        Returns:
            Dict with 'chart_type', 'x_column', 'y_columns', 'title'.
        """
        data_preview = json.dumps(
            {"columns": columns, "sample_rows": sample_data[:10]}, indent=2
        )

        system_prompt = """You are a data visualization expert. Given a question and query results, suggest the best chart type and configuration.

RESPOND WITH ONLY valid JSON (no markdown, no backticks) in this format:
{
    "chart_type": "bar|line|pie|doughnut|scatter|horizontalBar",
    "x_column": "column_name_for_x_axis",
    "y_columns": ["column_name_for_y_axis"],
    "title": "Human-readable chart title",
    "reasoning": "Brief explanation of why this chart type was chosen"
}

GUIDELINES:
- Use BAR for comparisons between categories
- Use LINE for time series / trends
- Use PIE/DOUGHNUT for proportions/percentages (max 8 slices)
- Use SCATTER for correlations between two numeric values
- Use HORIZONTAL BAR for many categories or long labels
- x_column should be the label/category column
- y_columns should be the numeric/value columns"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nData:\n{data_preview}",
                },
            ],
            temperature=0.0,
            max_tokens=500,
        )

        text = response.choices[0].message.content.strip()

        # Clean up markdown if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback: default to bar chart
            return {
                "chart_type": "bar",
                "x_column": columns[0] if columns else "label",
                "y_columns": columns[1:2] if len(columns) > 1 else columns[:1],
                "title": question,
                "reasoning": "Default fallback to bar chart.",
            }
