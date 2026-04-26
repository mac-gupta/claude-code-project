"""
General-purpose win-loss ICP agent.
Works with any CSV that has at least:
  - an outcome column (win/loss/won/lost)
  - a numeric deal value column
  - one or more categorical segmentation columns

Usage:
  python3 winloss_agent.py                        # prompts for CSV path
  python3 winloss_agent.py win_loss_data.csv      # loads directly
"""

import sys
import csv
import json
import anthropic
from collections import defaultdict

client = anthropic.Anthropic()

# ── CSV loading ──────────────────────────────────────────────────────────────

def load_csv(path: str) -> tuple[list[dict], list[str]]:
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])

# ── Schema detection ─────────────────────────────────────────────────────────

def detect_schema(rows: list[dict], columns: list[str]) -> dict:
    """
    Ask Claude to map columns to roles:
      outcome_col, value_col, cycle_col, dimension_cols
    Returns a schema dict.
    """
    sample = rows[:5]
    prompt = f"""You are analyzing a B2B sales CSV. Here are the column names and a few sample rows.

Columns: {columns}

Sample rows:
{json.dumps(sample, indent=2)}

Identify:
1. outcome_col: which column contains win/loss outcome (values like Won/Lost/Win/Loss/1/0)
2. value_col: which column contains deal value or revenue (numeric)
3. cycle_col: which column contains sales cycle length in days (numeric), or null if absent
4. dimension_cols: list of categorical columns useful for segmentation (company type, industry, persona, region, product, lead source, etc.)

Respond with ONLY a JSON object, no explanation:
{{
  "outcome_col": "column_name",
  "win_values": ["Won", "Win"],
  "value_col": "column_name",
  "cycle_col": "column_name_or_null",
  "dimension_cols": ["col1", "col2", ...]
}}"""

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    # Strip markdown code fences if present
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)

# ── Analysis engine ──────────────────────────────────────────────────────────

class WinLossAnalyzer:
    def __init__(self, rows: list[dict], schema: dict):
        self.rows = rows
        self.schema = schema
        self.outcome_col = schema["outcome_col"]
        self.win_values  = {v.lower() for v in schema.get("win_values", ["won", "win", "1", "true"])}
        self.value_col   = schema["value_col"]
        self.cycle_col   = schema.get("cycle_col")
        self.dim_cols    = schema["dimension_cols"]

    def is_win(self, row: dict) -> bool:
        return str(row.get(self.outcome_col, "")).lower() in self.win_values

    def _safe_float(self, row: dict, col: str) -> float | None:
        try:
            return float(row[col])
        except (KeyError, ValueError, TypeError):
            return None

    def summary(self) -> dict:
        total = len(self.rows)
        wins  = [r for r in self.rows if self.is_win(r)]
        values = [v for r in self.rows if (v := self._safe_float(r, self.value_col)) is not None]
        out = {
            "total_deals":      total,
            "wins":             len(wins),
            "losses":           total - len(wins),
            "win_rate":         round(len(wins) / total, 2) if total else 0,
            "avg_deal_value":   round(sum(values) / len(values)) if values else None,
            "available_dimensions": self.dim_cols,
        }
        if self.cycle_col:
            cycles = [v for r in self.rows if (v := self._safe_float(r, self.cycle_col)) is not None]
            out["avg_cycle_days"] = round(sum(cycles) / len(cycles), 1) if cycles else None
        return out

    def analyze_by(self, column: str, min_deals: int = 2) -> list[dict]:
        if column not in self.dim_cols and column not in [r.keys() for r in self.rows[:1]]:
            return [{"error": f"Column '{column}' not in dimension_cols: {self.dim_cols}"}]

        buckets: dict[str, list] = defaultdict(list)
        for r in self.rows:
            val = r.get(column, "")
            if val:
                buckets[val].append(r)

        values_all = [v for r in self.rows if (v := self._safe_float(r, self.value_col)) is not None]
        if not values_all:
            return [{"error": "No numeric deal values found"}]
        max_val   = max(values_all)

        cycles_all = []
        if self.cycle_col:
            cycles_all = [v for r in self.rows if (v := self._safe_float(r, self.cycle_col)) is not None]
        min_cycle = min(cycles_all) if cycles_all else None

        results = []
        for key, deals in buckets.items():
            if len(deals) < min_deals:
                continue
            wins     = [d for d in deals if self.is_win(d)]
            win_rate = len(wins) / len(deals)
            d_values = [v for d in deals if (v := self._safe_float(d, self.value_col)) is not None]
            avg_val  = sum(d_values) / len(d_values) if d_values else 0

            score_parts = [win_rate, avg_val / max_val if max_val else 0]
            if min_cycle and self.cycle_col:
                d_cycles = [v for d in deals if (v := self._safe_float(d, self.cycle_col)) is not None]
                avg_cyc  = sum(d_cycles) / len(d_cycles) if d_cycles else None
                if avg_cyc:
                    score_parts.append(min_cycle / avg_cyc)
                    results.append({
                        "segment":         key,
                        "n":               len(deals),
                        "win_rate":        round(win_rate, 2),
                        "avg_deal_value":  round(avg_val),
                        "avg_cycle_days":  round(avg_cyc, 1),
                        "score":           round(sum(score_parts) / len(score_parts), 4),
                    })
                    continue
            results.append({
                "segment":        key,
                "n":              len(deals),
                "win_rate":       round(win_rate, 2),
                "avg_deal_value": round(avg_val),
                "score":          round(sum(score_parts) / len(score_parts), 4),
            })

        return sorted(results, key=lambda x: -x["score"])

    def get_deals(self, outcome: str = None, filters: dict = None, limit: int = 25) -> list[dict]:
        rows = self.rows
        if outcome:
            want_win = outcome.lower() in ("won", "win", "w")
            rows = [r for r in rows if self.is_win(r) == want_win]
        if filters:
            for k, v in filters.items():
                rows = [r for r in rows if str(r.get(k, "")).lower() == v.lower()]
        return rows[:limit]

    def segment_detail(self, column: str, value: str) -> dict:
        deals = [r for r in self.rows if str(r.get(column, "")).lower() == value.lower()]
        wins  = [r for r in deals if self.is_win(r)]
        if not deals:
            return {"error": f"No deals found where {column}={value}"}

        # Collect unique values for other dimension columns
        other_dims = {}
        for col in self.dim_cols:
            if col == column:
                continue
            counts: dict[str, int] = defaultdict(int)
            for r in wins:
                v = r.get(col, "")
                if v:
                    counts[v] += 1
            if counts:
                other_dims[col] = dict(sorted(counts.items(), key=lambda x: -x[1])[:5])

        d_values = [v for r in deals if (v := self._safe_float(r, self.value_col)) is not None]
        return {
            "segment":         f"{column}={value}",
            "total_deals":     len(deals),
            "wins":            len(wins),
            "win_rate":        round(len(wins) / len(deals), 2),
            "avg_deal_value":  round(sum(d_values) / len(d_values)) if d_values else None,
            "top_co_occurring": other_dims,
        }

# ── Tool dispatch ────────────────────────────────────────────────────────────

def make_tools(dim_cols: list[str]) -> list[dict]:
    return [
        {
            "name": "summary_stats",
            "description": "Overall dataset summary: total deals, win rate, avg deal value, available dimensions.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "analyze_by",
            "description": (
                "Score and rank segments along any categorical column. "
                f"Available dimension columns: {dim_cols}. "
                "Returns win rate, avg deal value, avg cycle (if available), and composite score."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "column":    {"type": "string", "description": f"Column to group by. One of: {dim_cols}"},
                    "min_deals": {"type": "integer", "description": "Min deals to include a segment. Default 2."},
                },
                "required": ["column"],
            },
        },
        {
            "name": "segment_detail",
            "description": "Deep-dive on a specific segment value: win rate, avg deal, and which other dimensions co-occur with wins.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "column": {"type": "string", "description": "Column name"},
                    "value":  {"type": "string", "description": "Segment value to drill into"},
                },
                "required": ["column", "value"],
            },
        },
        {
            "name": "get_deals",
            "description": "Retrieve raw deal records, optionally filtered by outcome (Won/Lost) and field values.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "outcome": {"type": "string", "enum": ["Won", "Lost"]},
                    "filters": {"type": "object", "description": "Column → value pairs to filter by"},
                    "limit":   {"type": "integer", "description": "Max rows to return. Default 25."},
                },
            },
        },
    ]

# ── Agent loop ───────────────────────────────────────────────────────────────

SYSTEM_TEMPLATE = """You are a win-loss ICP analyst. You have access to a B2B sales dataset \
with the following schema:

- Outcome column: {outcome_col} (win values: {win_values})
- Deal value column: {value_col}
- Sales cycle column: {cycle_col}
- Segmentation dimensions: {dim_cols}

Use the tools to answer questions. Always cite numbers. Surface the most actionable insight first. \
Flag findings where sample size is small (n < 5)."""

def run_agent(analyzer: WinLossAnalyzer, schema: dict):
    tools = make_tools(analyzer.dim_cols)
    system = SYSTEM_TEMPLATE.format(
        outcome_col = schema["outcome_col"],
        win_values  = schema.get("win_values", ["Won"]),
        value_col   = schema["value_col"],
        cycle_col   = schema.get("cycle_col", "not present"),
        dim_cols    = analyzer.dim_cols,
    )

    def dispatch(name: str, inp: dict) -> str:
        if name == "summary_stats":
            return json.dumps(analyzer.summary(), indent=2)
        if name == "analyze_by":
            return json.dumps(analyzer.analyze_by(inp["column"], inp.get("min_deals", 2)), indent=2)
        if name == "segment_detail":
            return json.dumps(analyzer.segment_detail(inp["column"], inp["value"]), indent=2)
        if name == "get_deals":
            return json.dumps(analyzer.get_deals(inp.get("outcome"), inp.get("filters"), inp.get("limit", 25)), indent=2)
        return json.dumps({"error": f"Unknown tool: {name}"})

    messages = []

    def chat(user_text: str) -> str:
        messages.append({"role": "user", "content": user_text})
        while True:
            resp = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
                thinking={"type": "adaptive"},
            )
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "end_turn":
                return next((b.text for b in resp.content if b.type == "text"), "")
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     dispatch(block.name, block.input),
                    })
            messages.append({"role": "user", "content": results})

    print(f"\nDataset loaded. Dimensions: {', '.join(analyzer.dim_cols)}")
    print("Ask anything about your win-loss data. Type 'quit' to exit.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue
        print(f"\nAgent: {chat(user_input)}\n")

# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else input("CSV file path: ").strip()
    print(f"Loading {path}...")
    rows, columns = load_csv(path)
    print(f"  {len(rows)} rows, {len(columns)} columns: {columns}")

    print("Detecting schema...")
    schema = detect_schema(rows, columns)
    print(f"  Outcome: {schema['outcome_col']} (wins = {schema['win_values']})")
    print(f"  Value:   {schema['value_col']}")
    print(f"  Cycle:   {schema.get('cycle_col', 'not detected')}")
    print(f"  Dims:    {schema['dimension_cols']}")

    analyzer = WinLossAnalyzer(rows, schema)
    run_agent(analyzer, schema)

if __name__ == "__main__":
    main()
