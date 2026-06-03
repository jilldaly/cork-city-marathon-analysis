# Cork City Marathon Analysis Report Generator

A Python-based report generator for the Analog Devices Cork City Marathon, producing detailed PDF analysis reports of race results from 2024–2026.

## Features

### Single-Year Reports (`generate_single_year_report.py`)
- **Cover page** with summary table and gender split chart
- **Per-race sections** (Marathon, Half Marathon, 10K):
  - Key statistics tables
  - Finish-time distributions
  - Age-group charts (male and female breakdowns)
- **Club analysis**:
  - Club affiliation rates
  - Top clubs per race
  - Combined club rankings across all races
  - **Club word cloud** — visual representation of all participating clubs
  - Venn diagram showing club overlap between races

### Multi-Year Reports (`generate_report.py`)
- **Participation trends** across 2024–2026
- **Finish-time analysis** by year, gender, and race
- **Female participation trends**
- **Age-group breakdowns and trends**
- **Club word cloud** across all years

## Requirements

### System Dependencies
- **macOS**: `brew install poppler`
- **Ubuntu/Debian**: `sudo apt install poppler-utils`

### Python Dependencies
```bash
pip install -r requirements.txt
```

Key packages:
- `matplotlib` — charting and visualization
- `pandas` — data analysis
- `reportlab` — PDF generation
- `numpy` — numerical computing
- `wordcloud` — club word cloud visualization

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

### Single-Year Report
Generate a detailed report for a specific year:

```bash
python generate_single_year_report.py --year 2026
python generate_single_year_report.py --year 2025 --data data/cork --out report_charts/2025_report.pdf
```

Options:
- `--year` (required): Race year (e.g. 2026)
- `--data`: Base data directory (default: `data/cork`)
- `--out`: Output PDF path (default: `report_charts/cork_marathon_<year>_single.pdf`)

### Multi-Year Report
Generate a cross-year analysis report:

```bash
python generate_report.py
python generate_report.py --data data/cork --out report_charts/analysis.pdf
```

Options:
- `--data`: Directory containing year subdirectories (default: `data/cork`)
- `--out`: Output PDF path (default: `report_charts/cork_marathon_analysis.pdf`)

## Output

Reports are saved as PDF files to `report_charts/` by default.

### Single-Year Report Pages
- Page 1: Cover with summary
- Pages 2–4: Full Marathon, Half Marathon, 10K details
- Pages 5–7: Club analysis, affiliation, rankings
- Page 8: **Club word cloud** (all clubs)
- Page 9: Club overlap Venn diagram

### Multi-Year Report Pages
- Page 1: Cover with 3-year summary
- Pages 2–3: Participation trends
- Pages 4–5: Finish-time analysis
- Pages 6–7: Age-group analysis
- Page 8: **Club word cloud** (all clubs, all years)
- Final page: Key insights

## Project Structure

```
cork_city_marathon_2026/
├── generate_report.py              # Multi-year report generator
├── generate_single_year_report.py  # Single-year report generator
├── requirements.txt                # Python dependencies
├── data/cork/                      # Race result PDFs (not committed)
├── report_charts/                  # Generated PDF reports
├── README.md                       # This file
└── .gitignore
```

## How It Works

1. **PDF Conversion**: Uses `pdftotext` (poppler) to extract text from PDF result files
2. **Parsing**: Extracts finisher records (name, club, sex, age group, finish time)
3. **Analysis**: Computes statistics, trends, and groupings
4. **Visualization**: Generates charts using matplotlib
5. **PDF Assembly**: Uses reportlab to build final multi-page PDF report

## Notes

- The word cloud library is optional; a fallback matplotlib-based visualization is used if not installed
- Large PDF files may take 1–2 minutes to parse and convert
- All generated PDFs are saved with high DPI (150) for print quality

## License

Data sourced from official Cork City Marathon timing results.

## Author

Analysis report generator for Analog Devices Cork City Marathon 2024–2026.
