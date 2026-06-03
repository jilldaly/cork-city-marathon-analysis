# Cork City Marathon Analysis Report Generator

A Python-based report generator for the Analog Devices Cork City Marathon, producing detailed PDF analysis reports of race results from 2024–2026.

## Features

### Combined Report (`generate_combined_report.py`) — recommended
- **Cover page** with title and section contents
- **Section 1 — Overall Marathon Analysis** (latest year):
  - Summary table and gender split chart
  - Per-race pages (Marathon, Half Marathon, 10K): stats tables, finish-time distributions, age-group charts
- **Section 2 — Marathon Trend Analysis** (all years):
  - Total finishers trend per race
  - Female and male participation % trends
  - Finisher count by race and gender
  - Median finish time trends by race and gender
  - Age group participation trends
  - Age group median finish time trends
  - Finish time distribution boxplots per race
  - **Key Insights page** — auto-generated analysis of participation growth, gender balance, time stability, and performance spread
- **Section 3 — All Clubs Overall Analysis** (latest year):
  - Club affiliation rates and word cloud
  - Club overlap Venn diagram with region breakdown table
  - Club team performance — average top-5 finish time (clubs with ≥5 finishers)
  - Age group heatmaps (overall, per race; clubs with ≥15 finishers for Full/10K, ≥20 for Half)
  - Top clubs per race and combined ranking
- **Section 4 — All Clubs Trend Analysis** (all years):
  - Club count and affiliation rate trends
  - Top clubs trend across years
- **Section 5 — Per-club deep dive** (one per `--club` argument):
  - Overview: summary table, gender split per race, overall age breakdown, age × race heatmaps
  - Per-race pages: stats table, finish time vs field, age group breakdown
  - Club trend: multi-year participation and median time trends
  - **Finish Time Analysis + Key Insights** (always last): KDE curves vs field, gender KDE split, auto-generated club insights

### Single-Year Report (`generate_single_year_report.py`)
- Cover page with summary table and gender split
- Per-race sections (Marathon, Half Marathon, 10K):
  - Key statistics tables with colour-coded fastest/median times
  - Finish-time distributions (15-min buckets; 5-min for 10K)
  - Age-group count and median-time charts (male and female)
- Club analysis: affiliation rates, word cloud, Venn diagram, team performance, heatmaps, top clubs
- **Optional club deep dive** (`--club`): overview, per-race stats, KDE finish time analysis, key insights

### Multi-Year Report (`generate_report.py`)
- Participation and finish-time trends across 2024–2026
- Age-group breakdowns and club word cloud

## Requirements

### System Dependencies
- **macOS**: `brew install poppler`
- **Ubuntu/Debian**: `sudo apt install poppler-utils`

### Python Dependencies
```bash
pip install -r requirements.txt
```

Key packages: `matplotlib`, `pandas`, `reportlab`, `numpy`, `scipy`, `wordcloud`

## Data Structure

```
data/cork/
├── 2024/
│   ├── 02ResultsResults_full.pdf
│   ├── 02ResultsResults_half.pdf
│   └── 02ResultsResults_10k.pdf
├── 2025/
│   ├── cc_results_full_2025.pdf
│   ├── 02ResultsResults_half.pdf
│   └── 02ResultsResults_10k.pdf
└── 2026/
    ├── ResultListsPURFullResults.pdf
    ├── ResultListsPURFullResults_half.pdf
    └── ResultListsPURFullResults10km.pdf
```

## Usage

### Combined Report (recommended)

```bash
# Full report, latest year
python generate_combined_report.py

# With one or more club deep dives
python generate_combined_report.py --club "Togher A.C."
python generate_combined_report.py --club "Togher A.C." "Eagle A.C." "Leevale A.C."

# Custom year or output path
python generate_combined_report.py --year 2025 --out report_charts/combined_2025.pdf
```

Options:
- `--year`: Most recent year for single-year sections (default: `2026`)
- `--data`: Base data directory (default: `data/cork`)
- `--out`: Output PDF path (default: `report_charts/analog_devices_cork_marathon_analysis.pdf`)
- `--club`: One or more club names for deep dive + trend sections (optional)

### Single-Year Report

```bash
python generate_single_year_report.py --year 2026
python generate_single_year_report.py --year 2026 --club "Togher A.C." "Eagle A.C."
python generate_single_year_report.py --year 2026 --club "Eagle A.C." --out report_charts/eagle_2026.pdf
```

Options:
- `--year` (required): Race year (e.g. 2026)
- `--data`: Base data directory (default: `data/cork`)
- `--out`: Output PDF path (default: `report_charts/cork_marathon_<year>_single.pdf`)
- `--club`: One or more club names for deep dive sections (optional)

Club names use fuzzy matching — minor spelling differences are handled. If no match is found the script prints available club names.

### Multi-Year Report

```bash
python generate_report.py
python generate_report.py --data data/cork --out report_charts/analysis.pdf
```

## Project Structure

```
cork_city_marathon_2026/
├── generate_combined_report.py     # Combined report (recommended)
├── generate_single_year_report.py  # Single-year report + shared chart functions
├── generate_report.py              # Standalone multi-year trend report
├── requirements.txt                # Python dependencies
├── data/cork/                      # Race result PDFs (not committed)
├── report_charts/                  # Generated PDF reports
└── README.md
```

## How It Works

1. **PDF Conversion**: Uses `pdftotext` (poppler) to extract text from result PDFs
2. **Parsing**: Extracts finisher records — name, club, sex, age group, finish time
3. **Analysis**: Computes statistics, trends, and groupings across years and clubs
4. **Visualization**: Generates charts using matplotlib (KDE, histograms, heatmaps, boxplots, line/bar charts)
5. **PDF Assembly**: Builds the final multi-page PDF using reportlab

## Notes

- Word cloud is optional — a fallback chart is used if `wordcloud` is not installed
- Large PDFs may take 1–2 minutes to parse
- All charts are rendered at 150 DPI for print quality

## License

Data sourced from official Cork City Marathon timing results.

## Author

Analysis report generator for Analog Devices Cork City Marathon 2024–2026.

## Credits

- Designed with [Claude Cowork](https://claude.ai)
- Generated in [Claude Code](https://claude.ai/code)
- Grafted by a Human
