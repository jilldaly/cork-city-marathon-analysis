# Marathon Race Analytics — AI-Assisted Data Engineering Project
## Claude Code Project Prompt (v2)

---

## Project Vision

This project is a **portfolio-grade, AI-assisted data engineering system** for marathon race analytics. It processes race result PDFs, builds a structured data pipeline, generates a multi-page PDF analysis report, and serves an interactive web application — all reproducibly from a single command.

It is designed to be:
- **Useful to athletes** — personal performance lookup, club comparisons, age-grade analysis
- **Extensible to multiple cities and years** — Cork, Dublin, London, Boston, etc.
- **A showcase of modern AI-assisted engineering** — medallion architecture, agent harness design, ADRs, and CI/CD

The project will be published on GitHub, written about on Substack and LinkedIn, and hosted as a live application. It serves as a demonstration of how AI agents can accelerate real-world data engineering projects.

---

## Addy Osmani Agent Principles

This project follows the principles from:
- [Agentic Engine Optimization](https://addyosmani.com/blog/agentic-engine-optimization/) — structure code so AI agents can navigate, understand, and modify it accurately
- [agents.md](https://addyosmani.com/blog/agents-md/) — maintain an `AGENTS.md` file at the repo root that tells any AI agent exactly how this codebase works
- [Agent Harness Engineering](https://addyosmani.com/blog/agent-harness-engineering/) — build scaffolding that lets agents run safely, with guardrails, dry-run modes, and test coverage

Additionally, reference:
- [Microsoft Prompt Caching](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching) — avoid re-processing unchanged data
- [Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit) — audit trails, versioning, and safe agent handoffs

### `AGENTS.md` (generate this file)

Create `AGENTS.md` at the repo root. It must contain:
- What this project does in plain English (2–3 sentences)
- The entry points and what each does
- What the data layers are and where they live
- What tests exist and how to run them
- What the agent should never do (e.g., modify raw bronze PDFs, delete silver JSON cache without `--force`)
- Which files are safe to regenerate vs which are source-of-truth
- The coding conventions used (type hints, docstrings, file naming)

---

## Architecture: Medallion Data Layers

```
Bronze  →  Silver  →  Gold
PDFs       JSON        PDF Report
           cache       FastAPI
                       Streamlit
```

| Layer | Format | Location | Description |
|-------|--------|----------|-------------|
| **Bronze** | PDF | `data/{city}/{year}/*.pdf` | Raw downloads from race organisers. Never modified. |
| **Silver** | JSON | `data/{city}/{year}/silver/*.json` | Normalised, enriched records. Source of truth for all analysis. |
| **Gold** | PDF, API, UI | `outputs/`, `api/`, `app/` | Reports, endpoints, and dashboards built from silver layer. |

### Architecture Decision Records (ADRs)

Create `docs/adr/` and generate the following ADR files:

**ADR-001: Medallion Architecture**
- Decision: Bronze/Silver/Gold separation
- Rationale: Decouples extraction cost (PDF parsing) from analysis. Silver JSON is cheap to rebuild gold from. Bronze PDFs are immutable.
- Consequences: Adding a new chart or metric never requires re-parsing PDFs.

**ADR-002: JSON as Silver Layer**
- Decision: Store parsed records as JSON, not a relational database
- Rationale: Zero infrastructure dependency. JSON files are portable, version-controllable, and directly loadable by Python, FastAPI, and Streamlit. Migration to Postgres/DuckDB is a one-way step when scale demands it.
- Consequences: Queries over large datasets will be slower than SQL. Acceptable for <50k records per year.

**ADR-003: FastAPI for the data API**
- Decision: FastAPI over Flask or Django REST
- Rationale: Native async, automatic OpenAPI docs, type-validated with Pydantic, fast to stand up.
- Consequences: Requires Python 3.10+.

**ADR-004: Streamlit for the athlete-facing UI**
- Decision: Streamlit over React or Dash
- Rationale: Python-native, no frontend build step, rapid iteration, easy deployment on Streamlit Cloud.
- Consequences: Limited UI customisation compared to a React app. Acceptable for v1.

**ADR-005: Multi-city support via city field**
- Decision: Add `city` as a first-class field on every record
- Rationale: Allows cross-city comparison (Cork vs Dublin vs London) without schema changes.
- Consequences: All queries must filter or group by city. City slug used as folder name.

**ADR-006: Agent governance**
- Decision: All AI-generated code changes logged in `JOURNAL.md`
- Rationale: Demonstrates AI-assisted engineering for portfolio; provides audit trail.
- Consequences: Developer (or agent) must append to JOURNAL.md on each significant change.

---

## Repository Structure

```
marathon-analytics/
├── AGENTS.md                   # AI agent instructions (Addy Osmani pattern)
├── JOURNAL.md                  # How this project evolved — AI decisions log
├── README.md
├── CHANGELOG.md
├── .gitignore
├── requirements.txt
├── pyproject.toml
│
├── config/
│   ├── cities.yaml             # City registry
│   ├── county_map.py           # Club → Irish county (184 clubs, 2026 baseline)
│   ├── club_aliases.py         # Canonical club name deduplication
│   └── constants.py            # MIN_CLUB_SIZE=5, BUCKET_SECS=900, etc.
│
├── data/
│   ├── cork/
│   │   ├── 2026/
│   │   │   ├── ResultListsPURFullResults.pdf
│   │   │   ├── ResultListsPURFullResults_half.pdf
│   │   │   ├── ResultListsPURFullResults10km.pdf
│   │   │   ├── meta.yaml
│   │   │   └── silver/
│   │   │       ├── marathon.json
│   │   │       ├── half.json
│   │   │       └── km10.json
│   │   └── 2025/
│   │       └── ...
│   └── dublin/
│       └── ...
│
├── docs/
│   └── adr/
│       ├── ADR-001-medallion-architecture.md
│       ├── ADR-002-json-silver-layer.md
│       ├── ADR-003-fastapi.md
│       ├── ADR-004-streamlit.md
│       ├── ADR-005-multi-city.md
│       └── ADR-006-agent-governance.md
│
├── pipeline/
│   ├── __init__.py
│   ├── extract.py              # PDF → raw records (bronze → silver)
│   ├── enrich.py               # Add county, canonical club, gun/chip delta
│   ├── validate.py             # Data quality checks + quality report
│   ├── stats.py                # Per-race, per-club, per-AG, per-city statistics
│   └── cache.py                # Read/write silver JSON; mtime-based invalidation
│
├── reports/
│   ├── __init__.py
│   ├── charts.py               # All matplotlib chart functions (reusable)
│   ├── pdf_report.py           # reportlab PDF builder
│   └── templates/
│       └── cover.py            # Cover page layout
│
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── routers/
│   │   ├── races.py            # /races, /races/{year}
│   │   ├── athletes.py         # /athletes/search, /athletes/{name}
│   │   ├── clubs.py            # /clubs, /clubs/{name}/stats
│   │   └── cities.py           # /cities, /cities/{city}/compare
│   ├── models.py               # Pydantic schemas
│   └── dependencies.py         # Shared data loading
│
├── app/
│   ├── streamlit_app.py        # Main Streamlit entry point
│   └── pages/
│       ├── 01_overview.py
│       ├── 02_race_results.py
│       ├── 03_my_performance.py  # Athlete self-lookup
│       ├── 04_clubs.py
│       ├── 05_county_map.py
│       └── 06_year_on_year.py
│
├── tests/
│   ├── conftest.py
│   ├── test_extract.py
│   ├── test_enrich.py
│   ├── test_stats.py
│   ├── test_validate.py
│   └── test_api.py
│
├── run.py                      # CLI entry point
└── outputs/                    # Generated gold layer (gitignored except structure)
    └── .gitkeep
```

---

## `.gitignore`

```gitignore
# Bronze layer — raw PDFs (large, may have redistribution restrictions)
data/**/*.pdf

# Generated gold outputs (rebuilt on demand)
outputs/*.pdf
outputs/*.html

# Python
__pycache__/
*.pyc
.venv/
*.egg-info/

# Secrets
.env
*.key

# OS
.DS_Store

# Keep structure
!outputs/.gitkeep
!data/**/silver/*.json    # Silver JSON IS committed — source of truth
!data/**/meta.yaml
```

---

## `data/{city}/{year}/meta.yaml`

```yaml
year: 2026
city: cork
city_label: "Cork City"
event_name: "Analog Devices Cork City Marathon"
sponsor: "Analog Devices"
event_date: 2026-06-01
country: Ireland
currency: EUR
races:
  marathon:
    distance_km: 42.195
    file: ResultListsPURFullResults.pdf
  half:
    distance_km: 21.0975
    file: ResultListsPURFullResults_half.pdf
  km10:
    distance_km: 10.0
    file: ResultListsPURFullResults10km.pdf
notes: ""
```

---

## `config/cities.yaml`

```yaml
cities:
  cork:
    label: "Cork City Marathon"
    country: Ireland
    county_map: config/county_map.py   # Ireland-specific
  dublin:
    label: "Dublin City Marathon"
    country: Ireland
    county_map: config/county_map.py
  london:
    label: "London Marathon"
    country: UK
    county_map: null                   # future: UK region map
  boston:
    label: "Boston Marathon"
    country: USA
    county_map: null
```

---

## CLI Entry Point (`run.py`)

```bash
# Single year, single city
python run.py --city cork --year 2026

# Multiple years
python run.py --city cork --years 2024 2025 2026

# All available years for a city
python run.py --city cork --all

# All cities, all years
python run.py --all

# Flags
--force-reparse       # Ignore silver cache, re-extract from PDFs
--dry-run             # Validate inputs, print plan, no output written
--export-csv          # Also dump silver layer as flat CSV
--report-only         # Skip extraction, rebuild PDF from existing silver JSON
--quality-report      # Output data_quality.txt before generating reports
--no-pdf              # Skip PDF generation (faster, for dev)
```

---

## Silver Layer Schema

Each silver JSON file is a list of records:

```json
[
  {
    "year": 2026,
    "city": "cork",
    "race": "marathon",
    "sex": "F",
    "ag": "F40",
    "chip_secs": 10084,
    "gun_secs": 10085,
    "gun_chip_delta_secs": 1,
    "club": "Eagle A.C.",
    "club_canonical": "Eagle A.C.",
    "county": "Cork",
    "county_region": "Munster",
    "ni_club": false
  }
]
```

Fields:
| Field | Type | Notes |
|-------|------|-------|
| `year` | int | Race year |
| `city` | str | City slug — enables cross-city comparison |
| `race` | str | `"marathon"` \| `"half"` \| `"km10"` |
| `sex` | str | `"M"` \| `"F"` |
| `ag` | str | Age group: F, F35, F40 … M, M35, M40 … Wheelchair |
| `chip_secs` | int | Chip time in seconds |
| `gun_secs` | int | Gun time in seconds |
| `gun_chip_delta_secs` | int | Gun − Chip; measures start-line congestion |
| `club` | str | Raw club name from PDF, `""` if none |
| `club_canonical` | str | Deduplicated canonical name |
| `county` | str | From `county_map.py`; `""` if unmapped |
| `county_region` | str | Province: Munster, Leinster, Connacht, Ulster |
| `ni_club` | bool | True for Northern Ireland clubs |

---

## Step 1: Extraction (`pipeline/extract.py`)

Parse each PDF using `pdfplumber`. For each line containing two valid `HH:MM:SS` patterns:

1. Extract the two rightmost times → `chip_time`, `gun_time`
2. Find sex and age group using regex:
   ```
   \b(F75|F70|F65|F60|F55|F50|F45|F40|F35|M80|M75|M70|M65|M60|M55|M50|M45|M40|M35|Wheelc|F|M)\b
   ```
   Expect two matches: first = sex indicator, second = AG category
3. Extract club as text between the last ALL-CAPS surname token and the `{N}. {Sex}` position indicator
4. Compute `gun_chip_delta_secs = gun_secs - chip_secs`

Write output to `data/{city}/{year}/silver/{race}.json`.

---

## Step 2: Enrichment (`pipeline/enrich.py`)

For each record in silver JSON:

1. **Canonical club name** — apply `CLUB_ALIASES` dict:
   ```python
   CLUB_ALIASES = {
       "Bweeng Trail Blazers": "Bweeng Trail Blazers A.C.",
       "Galway City Harriers": "Galway City Harriers A.C.",
       "Kilkenny City Harriers": "Kilkenny City Harriers A.C.",
       # ... full list
   }
   ```
2. **County mapping** — look up `club_canonical` in `COUNTY_MAP`
3. **Province** — derive from county:
   ```python
   MUNSTER = {"Cork","Kerry","Limerick","Tipperary","Waterford","Clare"}
   LEINSTER = {"Dublin","Wicklow","Kildare","Wexford","Kilkenny","Carlow",
               "Meath","Louth","Westmeath","Offaly","Laois","Longford"}
   CONNACHT = {"Galway","Mayo","Roscommon","Sligo","Leitrim"}
   ULSTER_ROI = {"Donegal","Cavan","Monaghan"}
   ```
4. **NI flag** — `True` for clubs in `NI_CLUBS` dict

---

## Step 3: Validation (`pipeline/validate.py`)

After extraction and enrichment, write `outputs/data_quality_{city}_{year}.txt`:

```
=== Data Quality Report: Cork 2026 ===
Marathon:  2102 records parsed, 0 skipped
Half:      4309 records parsed, 0 skipped
10K:       3396 records parsed, 0 skipped

Club mapping:
  Mapped to county:  1450 / 1462 (99.2%)
  Unmapped clubs:    12 runners — see list below

Gun/chip delta:
  delta = 0:   847 runners (chip-timed start)
  delta > 0:   8114 runners (median delta: 38s)
  delta < 0:   3 runners (data anomaly — flagged)

Skipped lines: 0
```

Fail with a non-zero exit code if:
- Total records parsed < expected range (configurable per race in `meta.yaml`)
- More than 5% of clubs unmapped
- More than 10 records with `gun_chip_delta < 0`

---

## Step 4: Statistics (`pipeline/stats.py`)

Compute and cache (in memory / return dict) for each race × year × city:

- Total finishers, M/F split, M/F %
- Fastest, slowest, mean, median chip times — overall, by sex, by AG
- Finish time distribution in 15-min buckets — overall, M, F
- Age group counts and median times
- Club affiliation rate (% with club, unique clubs, runners per club)
- Top N clubs by count, with M/F breakdown
- Club median times (for clubs with ≥ `MIN_CLUB_SIZE` runners)
- County distribution — runner counts per county
- Venn diagram counts — clubs appearing in 1, 2, or all 3 races
- Gun/chip delta distribution — percentiles, median

---

## Step 5: PDF Report (`reports/pdf_report.py`)

Use `reportlab` for layout, `matplotlib` for chart images embedded as PNG.

**Design constants:**
```python
GREEN   = "#00843d"
AMBER   = "#f5a623"
MALE    = "#3b82f6"
FEMALE  = "#ec4899"
TOGHER  = "#b45309"   # example club highlight colour
```

**Pages (single-year):**
1. Cover — title, summary table, gender overview chart
2. Marathon — stats table, finish distribution, M/F age group counts + median times
3. Half Marathon — same structure
4. 10K — same structure
5. Club Analysis — affiliation stats, top clubs per race (sorted descending, M/F labels in bars)
6. Club Runners by County — county bar chart + per-race breakdown
7. Club Word Cloud — all clubs, font size ∝ sqrt(count)
8. Club Venn Diagram — 3-circle overlap + summary table
9. Club Spotlight — configurable (default: largest club by finishers)
   - Per-race: n, median, vs field median, % of field beaten, fastest, club rank
   - Distribution overlay histogram
   - Club comparison bar chart per race
10. *(Multi-year only)* Year-on-Year Trends — see below

**PDF design rules:**
- `KeepTogether` for all title + chart pairs — no orphan headings
- Club bar charts: sorted descending (highest count at top)
- In-bar labels: `M:x F:y` in white text, total at end
- Footer: event name + page number on every page
- Fonts: Helvetica, 7–9pt axis labels, 9–11pt chart titles, 14pt section headers

---

## Step 6: Multi-Year Trend Analysis

When `--years` or `--all` is passed with more than one year available:

### Trend Charts (add to PDF as final section; also expose via API)

All charts have a **year selector** on the Streamlit page.

- **Median finish time by year** — line chart, one line per sex, per race
  - X: year, Y: median time in minutes
  - Shows whether the field is getting faster or slower over time

- **Gender ratio by year** — grouped bar or area chart per race
  - X: year, Y: % female / % male
  - Tracks demographic change year over year

- **Participation volume by year** — line chart per race
  - X: year, Y: total finishers
  - Shows event growth or decline

- **Club affiliation rate by year** — line chart
  - X: year, Y: % of runners with a club listed

- **Top club rankings by year — Bump Chart**
  - X: year, Y: rank (1 = most finishers)
  - One line per club, top 10 clubs across all years
  - Tracks which clubs are growing or shrinking

- **Age group participation share by year** — stacked area chart
  - X: year, Y: % of finishers per AG
  - Tracks ageing of the participant base

- **Fastest time progression by year** — line chart, M and F
  - X: year, Y: winning time
  - Tracks course record progression

---

## FastAPI (`api/main.py`)

```python
# Key endpoints
GET  /api/v1/cities                         # Available cities
GET  /api/v1/{city}/years                   # Available years for city
GET  /api/v1/{city}/{year}/summary          # Race summary stats
GET  /api/v1/{city}/{year}/{race}/results   # Full results (paginated)
GET  /api/v1/{city}/{year}/{race}/clubs     # Club stats
GET  /api/v1/{city}/trends                  # Multi-year trend data
GET  /api/v1/athlete/search?name=Smith      # Athlete lookup across all years
GET  /api/v1/{city}/county-breakdown        # County distribution
GET  /api/v1/compare?cities=cork,dublin&year=2026  # Cross-city comparison
```

- All responses: JSON, typed with Pydantic
- Auto-generated OpenAPI docs at `/docs`
- CORS enabled for Streamlit
- Rate limiting via `slowapi`
- Cache responses for 1 hour (static data doesn't change)

---

## Streamlit App (`app/streamlit_app.py`)

**Pages:**

### 1. Overview
- City selector (dropdown), Year selector (multi-select)
- Summary stat cards across selected races
- Gender split stacked bar

### 2. Race Results
- Race selector (Marathon / Half / 10K)
- Finish time distribution (15-min buckets, M/F stacked)
- Age group breakdown
- Gun vs Chip scatter plot (congestion index)
  - X: overall finish position, Y: delta seconds
  - Colour by sex; tooltip shows name if available
  - Reveals start-line congestion pattern

### 3. My Performance *(athlete self-lookup)*
- Text search by name
- Returns: finish time, overall rank, gender rank, AG rank
- "You finished faster than X% of all finishers"
- "You finished faster than X% of {sex} finishers"
- "Compared to {AG} median: +/- Xm Xs"
- Download personal result card as PNG

### 4. Clubs
- Affiliation rate, unique clubs, county map
- Top clubs bar chart with M/F toggle
- Club spotlight: select any club → per-race performance vs field

### 5. County Map
- Horizontal bar chart with race filter toggle
- Table: county, runners, clubs, % of total

### 6. Year-on-Year *(activates with >1 year)*
- All trend charts from Step 6
- Year selector (checkboxes)

---

## Tests (`tests/`)

```python
# tests/test_extract.py
def test_parse_marathon_line_with_club():
    """Line with club should extract sex, ag, chip, gun, club"""

def test_parse_marathon_line_no_club():
    """Line without club should still extract sex, ag, chip, gun"""

def test_time_to_seconds():
    assert time_to_seconds("2:22:42") == 8562

def test_gun_chip_delta():
    """gun_secs >= chip_secs for all records"""

# tests/test_enrich.py
def test_club_alias_applied():
    """Bweeng Trail Blazers → Bweeng Trail Blazers A.C."""

def test_county_mapped_for_known_club():
    assert get_county("Eagle A.C.") == "Cork"

def test_ni_flag_set():
    assert get_county("Saintfield Striders") == "Down (NI)"
    assert is_ni_club("Saintfield Striders") is True

# tests/test_stats.py
def test_median_within_range():
    """Marathon median should be between 3:00 and 5:00"""

def test_gender_split_sums_to_total():
    stats = compute_stats(records)
    assert stats["male"] + stats["female"] == stats["total"]

def test_club_rank_ordered():
    clubs = get_top_clubs(records, n=10)
    counts = [c["count"] for c in clubs]
    assert counts == sorted(counts, reverse=True)

# tests/test_validate.py
def test_quality_report_generated():
def test_fails_on_low_record_count():
def test_flags_negative_gun_chip_delta():

# tests/test_api.py
def test_summary_endpoint_returns_200():
def test_athlete_search_returns_results():
def test_cross_city_compare_endpoint():
```

Run with: `pytest tests/ -v --tb=short`

---

## Data Quality Rules (`pipeline/validate.py`)

Exit non-zero if:
- Records parsed < minimum expected (set in `meta.yaml` per race)
- Club mapping rate < 95%
- Records with `gun_chip_delta < 0` > 10
- Any AG value not in the known set
- Duplicate bib numbers within a race

Warn (but continue) if:
- > 2% of lines skipped during extraction
- Any club appears with count = 1 (possible parsing artefact)

---

## Agent Governance

Following [Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit) principles:

### `JOURNAL.md` (append-only, generated by agent or developer)

```markdown
## 2026-06-01 — Project Initialisation
**Agent:** Claude (Sonnet 4.6) via Cowork
**Human:** Jill Daly
**Session summary:** Parsed 3 race PDFs for Cork 2026. Extracted 9,807 records.
Built HTML dashboard and PDF report. Identified 186 clubs, mapped to 28 counties.
Analysed Togher A.C. performance — fastest club in marathon and 10K.
**Key decisions:** Medallion architecture, JSON silver layer, pdfplumber for extraction.
**Files generated:** cork_marathon_2026_analysis.html, cork_marathon_2026_analysis.pdf
**What worked well:** pdfplumber line parsing, KeepTogether for PDF layout.
**What was hard:** Club name extraction from PDF (names adjacent to club, no delimiter).
  Solution: regex on last ALL-CAPS token before position indicator.

## 2026-06-XX — Refactor to Claude Code project
**Agent:** Claude Code
**Changes:** Restructured as full Python project with FastAPI, Streamlit, tests, ADRs.
```

### Prompt Caching Strategy

Following [Microsoft Prompt Caching](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching) guidance:
- Silver JSON is the cache — never re-parse a PDF if the JSON exists and the PDF mtime hasn't changed
- `cache.py` checks: `if silver_path.exists() and silver_mtime > pdf_mtime: load_silver()`
- `--force-reparse` bypasses this for debugging

---

## Hosting Plan

| Component | Platform | Notes |
|-----------|----------|-------|
| FastAPI | [Railway](https://railway.app) or [Render](https://render.com) | Free tier sufficient for v1 |
| Streamlit | [Streamlit Cloud](https://streamlit.io/cloud) | Free for public repos |
| Silver JSON | GitHub repo | Small files, version controlled |
| Bronze PDFs | Local only / private GitHub LFS | Not redistributed |

### `Procfile` (for Railway/Render)
```
web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

### `requirements.txt`
```
pdfplumber>=0.9
reportlab>=4.0
matplotlib>=3.7
numpy>=1.24
pypdf>=3.0
pyyaml>=6.0
fastapi>=0.110
uvicorn>=0.29
pydantic>=2.0
streamlit>=1.32
slowapi>=0.1
pytest>=8.0
httpx>=0.27         # for test_api.py
```

---

## Portfolio & Publishing Plan

### `README.md` should include:
- What the project does and why it's interesting
- Live demo link (Streamlit Cloud URL)
- API docs link (Railway URL + `/docs`)
- "Built with AI assistance" section — reference the Cowork session, Claude Code, tools used
- How to add a new city or year (2-step: add PDF to data folder, run `run.py`)
- Architecture diagram (generated from ADRs)

### Substack / LinkedIn Post Structure:
1. **The problem** — race results are PDFs. Athletes can't easily compare themselves.
2. **The approach** — medallion architecture, AI-assisted extraction, FastAPI + Streamlit.
3. **The interesting bits** — club name extraction from PDFs, county mapping, Venn diagram.
4. **The result** — live app, reproducible pipeline, extensible to any city.
5. **What I learned** — AI as a pair programmer, not an autocomplete.

---

## Appendix A: Cork 2026 Club → County Mapping (184 clubs)

The full mapping was verified in the 2026 analysis session. Key groups:

**Cork (71.9% of club runners — 1,042 runners):**
St. Finbarrs A.C., Togher A.C., Eagle A.C., Carrigaline A.C., FrontRunners Cork A.C.,
Grange/Fermoy A.C., Watergrasshill A.C., Midleton A.C., Leevale A.C., Mallow A.C.,
Glanmire A.C., Tracton A.C., Wibblies A.C., Aghada Running Club, Buttevant A.C.,
West Muskerry A.C., Ballincollig A.C., Donoughmore A.C., Bandon A.C., Duhallow A.C.,
Bweeng Trail Blazers A.C., Courcey A.C., East Cork A.C., Ballyvolane A.C.,
St. Nicholas A.C., Cork City A.C., Riverstick/Kinsale A.C., Cork Track Club A.C.,
Fota Island Running A.C., Bridevale A.C., North Cork A.C., Dromahane Road,
Shandrum A.C., Millstreet A.C., Clonakilty Road Runners, Doneraile A.C.,
Great Island Athletics A.C., Ballymore Cobh A.C., Doheny A.C., Durrus A.C.,
Mount Hillary A.C., Belgooly A.C., Blarney/Inniscara A.C., Carrigtwohill A.C.,
Rosscarbery Steam, St. Catherine's A.C., Beara A.C., Youghal A.C., Bantry A.C.,
Wibblies A.C., Nuenna A.C., Solid Running A.C., Polish Runners Club, The Churchtown

**Northern Ireland (confirmed, 7 runners across 5 clubs):**
- East Antrim Harriers → Antrim (NI) — Ballyclare
- Saintfield Striders → Down (NI) — Saintfield
- Ward Park Runners → Down (NI) — Bangor
- City of Derry Spartans → Derry (NI)
- Sperrin Harriers → Tyrone (NI) — Cookstown

All 184 clubs confirmed as island of Ireland only. No GB or international clubs in dataset.

---

## Appendix B: 2026 Baseline Statistics

```python
BASELINE_2026 = {
    "cork": {
        "marathon": {
            "total": 2102, "male": 1615, "female": 487,
            "fastest_m": "2:22:42", "fastest_f": "2:40:41",
            "median_overall": "3:57:09", "median_m": "3:51:09", "median_f": "4:17:09",
        },
        "half": {
            "total": 4309, "male": 2316, "female": 1993,
            "fastest_m": "1:09:27", "fastest_f": "1:14:35",
            "median_overall": "2:00:24", "median_m": "1:57:29", "median_f": "2:03:18",
        },
        "km10": {
            "total": 3396, "male": 1321, "female": 2075,
            "fastest_m": "0:30:58", "fastest_f": "0:32:16",
            "median_overall": "1:04:11", "median_m": "0:57:22", "median_f": "1:08:14",
        },
    }
}

TOGHER_2026 = {
    "marathon": {
        "n": 28, "median": "3:20:09", "field_median": "3:57:09",
        "vs_field": "-37m00s", "pct_field_beaten": 84,
        "fastest": "2:48:16", "club_rank": "1/8"
    },
    "half": {
        "n": 40, "median": "1:54:55", "field_median": "2:00:24",
        "vs_field": "-5m28s", "pct_field_beaten": 63,
        "fastest": "1:20:44", "club_rank": "6/10"
    },
    "km10": {
        "n": 27, "median": "0:47:34", "field_median": "1:04:11",
        "vs_field": "-16m37s", "pct_field_beaten": 90,
        "fastest": "0:36:51", "club_rank": "1/10"
    },
}

VENN_2026 = {
    "only_marathon": 36, "only_half": 49, "only_10k": 12,
    "mar_half": 31, "mar_10k": 5, "half_10k": 15, "all_three": 38
}

COUNTY_2026 = {
    "Cork": 1042, "Dublin": 94, "Tipperary": 44, "Wicklow": 40,
    "Waterford": 29, "Wexford": 27, "Limerick": 25, "Kerry": 23,
    "Galway": 17, "Meath": 11, "Mayo": 10, "Kildare": 9,
    "Westmeath": 9, "Kilkenny": 9, "Roscommon": 7, "Clare": 7,
    "Leitrim": 6, "Louth": 5, "Offaly": 5, "Monaghan": 5,
    "Down (NI)": 4, "Donegal": 4, "Carlow": 2, "Sligo": 1,
    "Antrim (NI)": 1, "Laois": 1, "Tyrone (NI)": 1, "Derry (NI)": 1,
}
```

---

## Prompt Strengthening Checklist

When an agent runs this prompt, it must:

- [ ] Generate `AGENTS.md` first, before writing any pipeline code
- [ ] Write `docs/adr/*.md` files before implementing the architecture they describe
- [ ] Use `MIN_CLUB_SIZE = 5` (from `config/constants.py`) everywhere — never hardcode
- [ ] Apply `CLUB_ALIASES` before `COUNTY_MAP` lookup — always use canonical name
- [ ] Run `pytest tests/` and confirm passing before marking task complete
- [ ] Append to `JOURNAL.md` at the end of each significant change
- [ ] Never modify files under `data/**/silver/` without user confirmation if they already exist
- [ ] The `--dry-run` flag must print a full plan and exit 0 without writing anything
- [ ] The `--export-csv` flag must dump one flat CSV per race per year to `outputs/`
- [ ] Gun vs Chip scatter plots must filter `delta < 0` records and note the count in the quality report
- [ ] `CHANGELOG.md` must get one entry per year of data added
- [ ] All chart functions in `reports/charts.py` must be independently callable (no side effects)
- [ ] FastAPI must have `/health` endpoint returning `{"status": "ok", "years": [...], "cities": [...]}`
- [ ] Streamlit "My Performance" page must handle name-not-found gracefully with a helpful message
