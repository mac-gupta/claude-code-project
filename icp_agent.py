import anthropic
import csv
import json
from collections import defaultdict

client = anthropic.Anthropic()

# ── Data loading ────────────────────────────────────────────────────────────

def load_data(path="win_loss_data.csv"):
    with open(path) as f:
        return list(csv.DictReader(f))

ROWS = load_data()

# ── Scoring helpers (from icp_analysis.py) ──────────────────────────────────

def size_bucket(r):
    n = int(r["company_size"])
    if n < 100:   return "SMB (<100)"
    if n < 500:   return "Mid-Market (100-499)"
    if n < 1000:  return "Upper-Mid (500-999)"
    return "Enterprise (1000+)"

def persona_tier(persona):
    c_suite = {"CEO", "CTO", "CFO", "COO", "CIO", "CISO"}
    vp = {"VP of Operations", "VP of IT", "VP of Digital", "VP of Marketing",
          "VP of Engineering", "Managing Partner", "Executive Director"}
    if persona in c_suite: return "C-Suite"
    if persona in vp:      return "VP / Head"
    return "Director / Manager"

def _analyze(rows, key_fn, min_deals=3):
    buckets = defaultdict(list)
    for r in rows:
        buckets[key_fn(r)].append(r)
    max_val  = max(float(r["deal_value"])       for r in rows)
    min_cycle= min(float(r["sales_cycle_days"]) for r in rows)
    results  = []
    for key, deals in buckets.items():
        if len(deals) < min_deals:
            continue
        wins     = [d for d in deals if d["outcome"] == "Won"]
        win_rate = len(wins) / len(deals)
        avg_val  = sum(float(d["deal_value"])       for d in deals) / len(deals)
        avg_cyc  = sum(float(d["sales_cycle_days"]) for d in deals) / len(deals)
        score    = round((win_rate + avg_val / max_val + min_cycle / avg_cyc) / 3, 4)
        results.append({
            "segment":         key,
            "n":               len(deals),
            "win_rate":        round(win_rate, 2),
            "avg_deal_value":  round(avg_val),
            "avg_cycle_days":  round(avg_cyc, 1),
            "score":           score,
        })
    return sorted(results, key=lambda x: -x["score"])

# ── Tool implementations ─────────────────────────────────────────────────────

DIMENSION_KEYS = {
    "industry":      lambda r: r["industry"],
    "company_size":  size_bucket,
    "lead_source":   lambda r: r["lead_source"],
    "persona":       lambda r: r["persona"],
    "persona_tier":  lambda r: persona_tier(r["persona"]),
    "product_tier":  lambda r: r["product_tier"],
    "department":    lambda r: r["department_initiating"],
    "use_case":      lambda r: r["use_case"],
}

def _analyze_by(dimension: str, min_deals: int = 3) -> str:
    if dimension not in DIMENSION_KEYS:
        return f"Unknown dimension. Choose from: {', '.join(DIMENSION_KEYS)}"
    return json.dumps(_analyze(ROWS, DIMENSION_KEYS[dimension], min_deals), indent=2)

def _persona_use_cases(persona: str = None) -> str:
    wins = [r for r in ROWS if r["outcome"] == "Won"]
    if persona:
        wins = [r for r in wins if r["persona"].lower() == persona.lower()]
    by_persona = defaultdict(list)
    for r in wins:
        by_persona[r["persona"]].append(r)
    out = {}
    for p, deals in sorted(by_persona.items(),
                            key=lambda x: -sum(float(d["deal_value"]) for d in x[1]) / len(x[1])):
        avg_val = sum(float(d["deal_value"]) for d in deals) / len(deals)
        out[p] = {
            "wins":           len(deals),
            "avg_deal_value": round(avg_val),
            "use_cases":      list({d["use_case"]      for d in deals}),
            "pain_points":    list({d["pain_point"]    for d in deals}),
            "trigger_events": list({d["trigger_event"] for d in deals}),
            "departments":    list({d["department_initiating"] for d in deals}),
        }
    return json.dumps(out, indent=2)

def _get_deals(outcome: str = None, filters: dict = None) -> str:
    rows = ROWS
    if outcome:
        rows = [r for r in rows if r["outcome"] == outcome]
    if filters:
        for k, v in filters.items():
            rows = [r for r in rows if r.get(k, "").lower() == v.lower()]
    return json.dumps(rows[:25], indent=2)

def _summary_stats() -> str:
    total = len(ROWS)
    wins  = sum(1 for r in ROWS if r["outcome"] == "Won")
    return json.dumps({
        "total_deals":          total,
        "wins":                 wins,
        "losses":               total - wins,
        "overall_win_rate":     round(wins / total, 2),
        "avg_deal_value":       round(sum(float(r["deal_value"])       for r in ROWS) / total),
        "avg_sales_cycle_days": round(sum(float(r["sales_cycle_days"]) for r in ROWS) / total, 1),
        "date_range":           f"{min(r['close_date'] for r in ROWS)} to {max(r['close_date'] for r in ROWS)}",
    }, indent=2)

# ── Tool registry ────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "analyze_by",
        "description": (
            "Score and rank segments along a given dimension. "
            "Returns win rate, avg deal value, avg sales cycle, and composite score. "
            "Dimensions: industry, company_size, lead_source, persona, persona_tier, "
            "product_tier, department, use_case."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "description": "One of: industry, company_size, lead_source, persona, "
                                   "persona_tier, product_tier, department, use_case"
                },
                "min_deals": {
                    "type": "integer",
                    "description": "Minimum deals in a segment to include it. Default 3.",
                }
            },
            "required": ["dimension"]
        }
    },
    {
        "name": "persona_use_cases",
        "description": (
            "Get use cases, pain points, and trigger events for winning personas. "
            "Optionally filter to a single persona title."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "persona": {
                    "type": "string",
                    "description": "e.g. 'CIO', 'COO'. Leave empty for all personas."
                }
            }
        }
    },
    {
        "name": "get_deals",
        "description": "Retrieve raw deal records, optionally filtered by outcome and field values.",
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "enum": ["Won", "Lost"]},
                "filters": {
                    "type": "object",
                    "description": "Field → value pairs, e.g. {\"industry\": \"Healthcare\", \"persona\": \"CIO\"}"
                }
            }
        }
    },
    {
        "name": "summary_stats",
        "description": "Overall dataset summary: total deals, win rate, average deal value and cycle.",
        "input_schema": {"type": "object", "properties": {}}
    },
]

TOOL_FNS = {
    "analyze_by":        lambda i: _analyze_by(i["dimension"], i.get("min_deals", 3)),
    "persona_use_cases": lambda i: _persona_use_cases(i.get("persona")),
    "get_deals":         lambda i: _get_deals(i.get("outcome"), i.get("filters")),
    "summary_stats":     lambda i: _summary_stats(),
}

# ── Agent loop ───────────────────────────────────────────────────────────────

SYSTEM = """You are an ICP (Ideal Customer Profile) analyst with access to a B2B software \
company's win-loss dataset (50 deals, Jan–Aug 2025). You help sales, marketing, and BDR teams \
understand which accounts to target, which personas to engage, and what messaging to use.

When answering:
- Call tools to pull data before drawing conclusions
- Cite specific numbers
- Highlight the most actionable insight first
- Flag anything counterintuitive or where sample size is small"""

def _run(messages: list) -> tuple[str, list]:
    while True:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if b.type == "text"), "")
            return text, messages

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = TOOL_FNS[block.name](block.input)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     result,
                })
        messages.append({"role": "user", "content": tool_results})

# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    print("ICP Agent  —  ask anything about your win-loss data.")
    print("Examples:")
    print("  - Which industry should we focus on?")
    print("  - What triggers a CIO to buy?")
    print("  - Write a cold call opener for a COO in Logistics.")
    print("  - Why is our win rate so low in Technology?\n")
    print("Type 'quit' to exit.\n")

    messages = []
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue
        messages.append({"role": "user", "content": user_input})
        answer, messages = _run(messages)
        print(f"\nAgent: {answer}\n")

if __name__ == "__main__":
    main()
