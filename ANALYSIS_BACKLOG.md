# Single Year Report — Analysis Backlog

Incremental additions to `generate_single_year_report.py`, roughly in priority order.

## Race Analysis
- [ ] **KDE smooth finish time curves** — M/F density overlay on the same axes, cleaner than histogram buckets
- [ ] **Pace zones** — % of field finishing in colour-coded bands (sub-3 / 3–4 / 4–5 / 5+ for full; scaled for half/10K)
- [ ] **Age vs median time curve** — line/scatter showing how performance changes with age, M and F separately
- [ ] **Gender time gap by age group** — bar chart of M–F median time difference per bracket (gap often closes in older groups)
- [ ] **Age group winners table** — fastest male and female per age bracket, with their time (no names if privacy required)

## Club Analysis
- [ ] **Club gender balance chart** — diverging horizontal bar (M left / F right), highlights clubs that skew heavily one way
- [ ] **Club performance vs size scatter** — x = finisher count, y = avg finish time; reveals clubs that punch above weight
- [ ] **Top club per age group** — table: which club has the fastest median in each age bracket, per race
- [ ] **Multi-race clubs** — clubs whose members ran more than one race on the day (requires linking by name/bib — privacy check needed)
- [ ] **Club improvement YoY** — requires multi-year data; compare club median time across 2024/2025/2026

## Deep Dive (future expansion)
- [ ] **Multi-club comparison** — overlay two or more clubs' finish distributions on the same chart
- [ ] **Club loyalty / retention** — members appearing in consecutive years (requires cross-year name matching — privacy check needed)
- [ ] **Newcomer clubs** — clubs appearing for the first time vs previous year

## Data / Infrastructure
- [ ] **DNF/DNS detection** — if source data includes starters, can compute dropout rate
- [ ] **Gun vs chip time analysis** — corral/start delay distribution (2026 data has both)
- [ ] **Bib-range analysis** — if bibs encode start wave, can analyse performance by wave
