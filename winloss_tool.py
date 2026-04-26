#!/usr/bin/env python3
"""
Data-only CLI for the /winloss Claude Code skill.
No LLM calls — Claude Code reads the JSON output and interprets it.

Commands:
  info    <csv>
  summary <csv> <outcome_col> <win_values> <value_col> [<cycle_col>]
  analyze <csv> <outcome_col> <win_values> <value_col> <by_col> [<cycle_col>] [<min_deals>]
  detail  <csv> <outcome_col> <win_values> <value_col> <dim_cols> <filter_col> <filter_val>
"""
import sys
import csv
import json
from collections import defaultdict


def load_csv(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def is_win(row, outcome_col, win_vals):
    return str(row.get(outcome_col, "")).lower() in win_vals


def safe_float(row, col):
    try:
        return float(row[col])
    except (KeyError, ValueError, TypeError):
        return None


def cmd_info(csv_path):
    rows, columns = load_csv(csv_path)
    col_info = {}
    for col in columns:
        vals = [r[col] for r in rows if r.get(col)]
        unique = sorted(set(vals))[:12]
        numeric = sum(1 for v in vals if safe_float({col: v}, col) is not None)
        col_info[col] = {
            "unique_sample": unique,
            "total_non_empty": len(vals),
            "looks_numeric": numeric > len(vals) * 0.8,
        }
    print(json.dumps({
        "total_rows": len(rows),
        "columns": columns,
        "sample_rows": rows[:5],
        "column_info": col_info,
    }, indent=2))


def cmd_summary(csv_path, outcome_col, win_values_str, value_col, cycle_col="none"):
    rows, columns = load_csv(csv_path)
    win_vals = {v.strip().lower() for v in win_values_str.split(",")}

    total = len(rows)
    wins = [r for r in rows if is_win(r, outcome_col, win_vals)]
    values = [v for r in rows if (v := safe_float(r, value_col)) is not None]

    skip = {outcome_col, value_col}
    if cycle_col and cycle_col != "none":
        skip.add(cycle_col)
    dim_cols = []
    for col in columns:
        if col in skip:
            continue
        unique = {r.get(col, "") for r in rows if r.get(col)}
        if 1 < len(unique) <= 25:
            dim_cols.append(col)

    result = {
        "total_deals": total,
        "wins": len(wins),
        "losses": total - len(wins),
        "win_rate": round(len(wins) / total, 2) if total else 0,
        "avg_deal_value": round(sum(values) / len(values)) if values else None,
        "dimension_cols": dim_cols,
    }
    if cycle_col and cycle_col != "none":
        cycles = [v for r in rows if (v := safe_float(r, cycle_col)) is not None]
        result["avg_cycle_days"] = round(sum(cycles) / len(cycles), 1) if cycles else None

    print(json.dumps(result, indent=2))


def cmd_analyze(csv_path, outcome_col, win_values_str, value_col, by_col,
                cycle_col="none", min_deals=2):
    rows, _ = load_csv(csv_path)
    win_vals = {v.strip().lower() for v in win_values_str.split(",")}
    min_deals = int(min_deals)

    values_all = [v for r in rows if (v := safe_float(r, value_col)) is not None]
    if not values_all:
        print(json.dumps({"error": "No numeric deal values found"}))
        return
    max_val = max(values_all)

    use_cycle = cycle_col and cycle_col != "none"
    cycles_all = [v for r in rows if use_cycle and (v := safe_float(r, cycle_col)) is not None]
    min_cycle = min(cycles_all) if cycles_all else None

    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        v = r.get(by_col, "")
        if v:
            buckets[v].append(r)

    results = []
    for key, deals in buckets.items():
        if len(deals) < min_deals:
            continue
        wins = [d for d in deals if is_win(d, outcome_col, win_vals)]
        win_rate = len(wins) / len(deals)
        d_vals = [v for d in deals if (v := safe_float(d, value_col)) is not None]
        avg_val = sum(d_vals) / len(d_vals) if d_vals else 0

        score_parts = [win_rate, avg_val / max_val if max_val else 0]
        row = {"segment": key, "n": len(deals),
               "win_rate": round(win_rate, 2), "avg_deal_value": round(avg_val)}

        if use_cycle and min_cycle:
            d_cycles = [v for d in deals if (v := safe_float(d, cycle_col)) is not None]
            if d_cycles:
                avg_cyc = sum(d_cycles) / len(d_cycles)
                score_parts.append(min_cycle / avg_cyc)
                row["avg_cycle_days"] = round(avg_cyc, 1)

        row["score"] = round(sum(score_parts) / len(score_parts), 4)
        results.append(row)

    print(json.dumps(sorted(results, key=lambda x: -x["score"]), indent=2))


def cmd_detail(csv_path, outcome_col, win_values_str, value_col,
               dim_cols_str, filter_col, filter_val):
    rows, _ = load_csv(csv_path)
    win_vals = {v.strip().lower() for v in win_values_str.split(",")}
    dim_cols = [c.strip() for c in dim_cols_str.split(",")]

    deals = [r for r in rows if str(r.get(filter_col, "")).lower() == filter_val.lower()]
    wins = [r for r in deals if is_win(r, outcome_col, win_vals)]

    if not deals:
        print(json.dumps({"error": f"No deals where {filter_col}={filter_val}"}))
        return

    co_occur = {}
    for col in dim_cols:
        if col == filter_col:
            continue
        counts: dict[str, int] = defaultdict(int)
        for r in wins:
            v = r.get(col, "")
            if v:
                counts[v] += 1
        if counts:
            co_occur[col] = dict(sorted(counts.items(), key=lambda x: -x[1])[:5])

    d_vals = [v for r in deals if (v := safe_float(r, value_col)) is not None]
    print(json.dumps({
        "filter": f"{filter_col}={filter_val}",
        "total_deals": len(deals),
        "wins": len(wins),
        "win_rate": round(len(wins) / len(deals), 2),
        "avg_deal_value": round(sum(d_vals) / len(d_vals)) if d_vals else None,
        "win_co_occurrences": co_occur,
    }, indent=2))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(json.dumps({"error": "No command given"}))
        sys.exit(1)

    cmd, rest = args[0], args[1:]
    try:
        if cmd == "info"    and len(rest) >= 1: cmd_info(*rest[:1])
        elif cmd == "summary" and len(rest) >= 4: cmd_summary(*rest[:5])
        elif cmd == "analyze" and len(rest) >= 5: cmd_analyze(*rest[:8])
        elif cmd == "detail"  and len(rest) >= 7: cmd_detail(*rest[:8])
        else:
            print(json.dumps({"error": f"Unknown command or missing args: {args}"}))
            sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
