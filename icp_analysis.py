import csv
from collections import defaultdict

def load_data(path):
    with open(path) as f:
        return list(csv.DictReader(f))

def score_segment(win_rate, avg_deal_value, avg_cycle_days,
                  max_value, min_cycle, n, min_deals=3):
    if n < min_deals:
        return None
    value_score = avg_deal_value / max_value
    cycle_score = min_cycle / avg_cycle_days
    return round((win_rate + value_score + cycle_score) / 3, 4)

def analyze(rows, group_key, min_deals=3):
    buckets = defaultdict(list)
    for r in rows:
        buckets[group_key(r)].append(r)

    max_value = max(float(r["deal_value"]) for r in rows)
    min_cycle = min(float(r["sales_cycle_days"]) for r in rows)

    results = []
    for key, deals in buckets.items():
        wins = [d for d in deals if d["outcome"] == "Won"]
        win_rate = len(wins) / len(deals)
        avg_value = sum(float(d["deal_value"]) for d in deals) / len(deals)
        avg_cycle = sum(float(d["sales_cycle_days"]) for d in deals) / len(deals)
        score = score_segment(win_rate, avg_value, avg_cycle,
                              max_value, min_cycle, len(deals), min_deals)
        if score is not None:
            results.append({
                "segment": key,
                "n": len(deals),
                "win_rate": round(win_rate, 2),
                "avg_deal_value": round(avg_value),
                "avg_cycle_days": round(avg_cycle, 1),
                "score": score,
                "deals": deals,
            })
    return sorted(results, key=lambda x: x["score"], reverse=True)

def persona_tier(persona):
    c_suite = {"CEO", "CTO", "CFO", "COO", "CIO", "CISO"}
    vp = {"VP of Operations", "VP of IT", "VP of Digital", "VP of Marketing",
          "VP of Engineering", "Managing Partner", "Executive Director"}
    if persona in c_suite: return "C-Suite"
    if persona in vp:      return "VP / Head"
    return "Director / Manager"

def top_values(deals, field, top_n=3):
    counts = defaultdict(int)
    for d in deals:
        if d["outcome"] == "Won":
            counts[d[field]] += 1
    return [v for v, _ in sorted(counts.items(), key=lambda x: -x[1])[:top_n]]

def print_table(title, rows, key="segment"):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")
    print(f"{'Segment':<32} {'N':>4} {'Win%':>6} {'Avg $':>9} {'Days':>6} {'Score':>7}")
    print(f"{'-'*32} {'-'*4} {'-'*6} {'-'*9} {'-'*6} {'-'*7}")
    for r in rows[:8]:
        print(f"{str(r[key]):<32} {r['n']:>4} {r['win_rate']*100:>5.0f}% "
              f"{r['avg_deal_value']:>9,} {r['avg_cycle_days']:>6.1f} {r['score']:>7.4f}")

def print_top_patterns(rows, field, title, top_n=10):
    wins = [r for r in rows if r["outcome"] == "Won"]
    all_deals = rows

    win_counts = defaultdict(int)
    total_counts = defaultdict(int)
    for r in wins:
        win_counts[r[field]] += 1
    for r in all_deals:
        total_counts[r[field]] += 1

    ranked = sorted(win_counts.items(), key=lambda x: -x[1])[:top_n]

    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")
    print(f"  {'Pattern':<52} {'Wins':>5}  {'Win%':>6}")
    print(f"  {'-'*52} {'-'*5}  {'-'*6}")
    for val, w in ranked:
        t = total_counts[val]
        print(f"  {val:<52} {w:>5}  {w/t*100:>5.0f}%")

def print_persona_use_cases(rows):
    wins = [r for r in rows if r["outcome"] == "Won"]
    by_persona = defaultdict(list)
    for r in wins:
        by_persona[r["persona"]].append(r)

    # Sort personas by deal value descending
    ranked = sorted(by_persona.items(), key=lambda x: -sum(float(d["deal_value"]) for d in x[1]) / len(x[1]))

    print(f"\n{'='*72}")
    print("  PERSONA USE CASES  (wins only, ranked by avg deal value)")
    print(f"{'='*72}")

    for persona, deals in ranked:
        avg_val = sum(float(d["deal_value"]) for d in deals) / len(deals)
        avg_days = sum(float(d["sales_cycle_days"]) for d in deals) / len(deals)
        tier = persona_tier(persona)

        use_cases  = top_values(deals + [d for d in rows if d["persona"] == persona and d["outcome"] == "Won"],
                                "use_case", 3)
        pains      = top_values(deals + [d for d in rows if d["persona"] == persona and d["outcome"] == "Won"],
                                "pain_point", 3)
        triggers   = top_values(deals + [d for d in rows if d["persona"] == persona and d["outcome"] == "Won"],
                                "trigger_event", 3)
        depts      = top_values(deals + [d for d in rows if d["persona"] == persona and d["outcome"] == "Won"],
                                "department_initiating", 2)

        print(f"\n  {persona}  [{tier}]  —  {len(deals)} wins  |  avg ${avg_val:,.0f}  |  avg {avg_days:.0f} days")
        print(f"  {'Use cases:':<14} {' / '.join(use_cases)}")
        print(f"  {'Pain points:':<14} {' / '.join(pains)}")
        print(f"  {'Triggers:':<14} {' / '.join(triggers)}")
        print(f"  {'Dept:':<14} {' / '.join(depts)}")

def main():
    rows = load_data("win_loss_data.csv")

    by_industry     = analyze(rows, lambda r: r["industry"])
    by_size         = analyze(rows, lambda r: (
        "SMB (<100)" if int(r["company_size"]) < 100 else
        "Mid-Market (100-499)" if int(r["company_size"]) < 500 else
        "Upper-Mid (500-999)" if int(r["company_size"]) < 1000 else
        "Enterprise (1000+)"
    ))
    by_source       = analyze(rows, lambda r: r["lead_source"])
    by_persona      = analyze(rows, lambda r: r["persona"])
    by_persona_tier = analyze(rows, lambda r: persona_tier(r["persona"]))
    by_dept         = analyze(rows, lambda r: r["department_initiating"])

    print_table("By Industry", by_industry)
    print_table("By Company Size", by_size)
    print_table("By Lead Source", by_source)
    print_table("By Persona (Decision Maker)", by_persona)
    print_table("By Persona Tier", by_persona_tier)
    print_table("By Department Initiating", by_dept)
    print_top_patterns(rows, "use_case",      "Top Use Cases (wins, by frequency)")
    print_top_patterns(rows, "trigger_event", "Top Trigger Events (wins, by frequency)")

    print_persona_use_cases(rows)

    # --- Final ICP ---
    print(f"\n{'='*72}")
    print("  RECOMMENDED ICP SUMMARY")
    print(f"{'='*72}")
    for label, ranked in [
        ("Industry",     by_industry),
        ("Company Size", by_size),
        ("Lead Source",  by_source),
        ("Persona",      by_persona),
        ("Persona Tier", by_persona_tier),
        ("Dept",         by_dept),
    ]:
        if ranked:
            t = ranked[0]
            print(f"  {label:<14}: {t['segment']:<34} win {t['win_rate']*100:.0f}%  "
                  f"avg ${t['avg_deal_value']:,}  {t['avg_cycle_days']}d")
    print()

if __name__ == "__main__":
    main()
