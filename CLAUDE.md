# B2B Win-Loss ICP Analysis

GitHub: https://github.com/mac-gupta/claude-code-project

## Files
- `win_loss_data.csv` — 50 sample deals with fields: deal_id, close_date, company_name, industry, company_size, deal_value, outcome, competitor, sales_rep, sales_cycle_days, lead_source, product_tier, primary_reason, persona, use_case, pain_point, trigger_event, department_initiating
- `icp_analysis.py` — segments and scores deals across win rate, avg deal value, and sales cycle; prints persona use case breakdown

## How to run
```bash
python3 icp_analysis.py
```

## ICP Summary (as of April 2026)
- **Best industries**: Energy, Healthcare, Logistics
- **Best company size**: Enterprise (1000+) and Upper-Mid (500–999)
- **Best lead sources**: Partner Referral, Referral, Inbound — Cold Outreach and Events = 0% win rate
- **Best personas**: CTO, CIO, COO — IT Director and Director/Manager tier = 0% win rate

## Next steps
- Lead scoring template to rank inbound accounts against ICP
- Persona cards (one-pager per buyer type with use cases, pain points, talk tracks)
- BDR call guide already drafted (in conversation history)
