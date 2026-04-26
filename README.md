# Win-Loss ICP Agent

A conversational AI agent that analyzes B2B win-loss data to surface your Ideal Customer Profile (ICP). Works with **any CSV** — bring your own deal data.

## What it does

Point it at a CSV with win/loss outcomes, deal values, and whatever segmentation columns you have (industry, company size, persona, region, product tier, etc.). The agent auto-detects your schema and lets you ask questions in plain English:

- *Which industry should we focus on?*
- *What's our win rate by company size?*
- *What triggers a VP of Engineering to buy?*
- *Why are we losing in the Technology vertical?*

## Prerequisites

**Python 3.10+** and an [Anthropic API key](https://console.anthropic.com/).

```bash
pip3 install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Usage

### Option 1 — Claude Code skill

If you have [Claude Code](https://claude.ai/code), clone the repo and use the `/winloss` slash command directly in your session:

```
/winloss /path/to/your/deals.csv
```

Claude Code auto-detects the schema, then you ask questions in plain English. No pip install needed.

### Option 2 — Standalone terminal agent

```bash
pip3 install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

python3 winloss_agent.py /path/to/your/deals.csv
```

Works anywhere — no Claude Code required.

---

Your CSV needs at minimum:
- An **outcome column** — values like Won/Lost, Win/Loss, 1/0
- A **deal value column** — numeric revenue or ACV
- At least one **categorical column** to segment by (industry, persona, region, etc.)

Sales cycle days is optional but improves scoring if present.

## Sample data

A 50-row synthetic B2B dataset is included (`win_loss_data.csv`) so you can try it immediately:

```bash
# Claude Code skill
/winloss win_loss_data.csv

# or standalone agent
python3 winloss_agent.py win_loss_data.csv
```

## How scoring works

Each segment is scored on a 0–1 composite:

```
score = (win_rate + avg_deal_value/max_deal_value + min_cycle/avg_cycle) / 3
```

Higher score = better fit for your ICP. Segments with fewer than 2 deals are excluded.

## Files

| File | Description |
|------|-------------|
| `.claude/commands/winloss.md` | Claude Code skill — invoke with `/winloss <csv>` |
| `winloss_tool.py` | Data CLI used by the skill (no API calls) |
| `winloss_agent.py` | Standalone terminal agent — works with any CSV |
| `icp_agent.py` | Agent hardcoded to the sample dataset schema |
| `icp_analysis.py` | Static analysis script (no chat, just prints tables) |
| `win_loss_data.csv` | 50-row sample B2B dataset |
