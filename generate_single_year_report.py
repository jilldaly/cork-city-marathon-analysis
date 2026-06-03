#!/usr/bin/env python3
"""
Cork City Marathon — Single-Year Race Analysis Report
======================================================
Generates a detailed PDF report for one race year, covering:
  • Cover page with summary table and gender split chart
  • Per-race pages (Marathon / Half Marathon / 10K):
      – Key stats table, finish-time distribution, age-group charts
  • Club analysis: affiliation rates, top clubs per race, combined ranking
  • Club word cloud
  • Club overlap Venn diagram

Expected directory layout (default data/cork/<year>/)
------------------------------------------------------
  2026/  ResultListsPURFullResults.pdf
         ResultListsPURFullResults_half.pdf
         ResultListsPURFullResults10km.pdf

  2025/  cc_results_full_2025.pdf
         02ResultsResults_half.pdf
         02ResultsResults_10k.pdf

  2024/  02ResultsResults_full.pdf
         02ResultsResults_half.pdf
         02ResultsResults_10k.pdf

Usage
-----
  python generate_single_year_report.py --year 2026
  python generate_single_year_report.py --year 2025 --data data/cork --out report_charts/

Requirements
------------
  pip install -r requirements.txt
  pip install wordcloud          # optional – word cloud page skipped if absent
  System: poppler-utils  (pdftotext)
    macOS:  brew install poppler
    Ubuntu: sudo apt install poppler-utils
"""

import argparse
import io
import os
import re
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Image, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

try:
    from wordcloud import WordCloud
    HAS_WORDCLOUD = True
except ImportError:
    HAS_WORDCLOUD = False

# ── Palette ───────────────────────────────────────────────────────────────────
C_GREEN  = '#1A7A4A'   # header green
C_BLUE   = '#4472C4'   # male blue
C_PINK   = '#E5498C'   # female pink
C_GOLD   = '#F0A500'   # fastest highlight
C_LIGHT  = '#F2F2F2'   # table stripe
C_DGREY  = '#404040'   # dark text

RACE_COLORS = {'Full': C_GREEN, 'Half': C_BLUE, '10K': C_GOLD}
RACES = ['Full', 'Half', '10K']

# File name maps per year
PDF_FILES = {
    2026: {
        'Full': 'ResultListsPURFullResults.pdf',
        'Half': 'ResultListsPURFullResults_half.pdf',
        '10K':  'ResultListsPURFullResults10km.pdf',
    },
    2025: {
        'Full': 'cc_results_full_2025.pdf',
        'Half': '02ResultsResults_half.pdf',
        '10K':  '02ResultsResults_10k.pdf',
    },
    2024: {
        'Full': '02ResultsResults_full.pdf',
        'Half': '02ResultsResults_half.pdf',
        '10K':  '02ResultsResults_10k.pdf',
    },
}

# ── Age group ordering for charts ─────────────────────────────────────────────
M_AG_ORDER = ['M','M35','M40','M45','M50','M55','M60','M65','M70','M75','M80']
F_AG_ORDER = ['F','F35','F40','F45','F50','F55','F60','F65','F70','F75','F80']

HMMSS_RE = re.compile(r'\b(\d{1,2}:\d{2}:\d{2})\b')
MMSS_RE  = re.compile(r'\b([3-9]\d:\d{2}|[1-9]\d\d:\d{2})\b')
SEX_RANK_RE = re.compile(r'\s+(\d+\.\s+([MF]))\s+')


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def time_to_sec(t):
    if not t:
        return None
    parts = t.strip().split(':')
    try:
        if len(parts) == 3:
            return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0])*60 + int(parts[1])
    except ValueError:
        return None


def sec_to_hms(s, short=False):
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return '—'
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sc  = divmod(rem, 60)
    if short and h == 0:
        return f"{m}:{sc:02d}"
    return f"{h}:{m:02d}:{sc:02d}"


def normalize_ag(ag_raw, sex):
    """Normalise any AG string to compact form: M, M35, M40 … F, F35, F40 …"""
    if not ag_raw:
        return sex
    ag = ag_raw.strip()
    # Already compact (2026): "F", "M35", "F40"
    if re.match(r'^[MF]\d*$', ag):
        return ag
    # Range form (2024/2025): "F18-34", "M35-39", "F Juvenile", "F Senior"
    m = re.match(r'^[MF](\d+)', ag)
    if m:
        decade = m.group(1)[:2]
        return sex if decade == '18' else sex + decade
    if re.search(r'Juvenile|Junior|Youth', ag, re.I):
        return sex + 'Juv'
    return sex   # Senior / unknown → open


def pdf_to_text(pdf_path, out_path):
    try:
        subprocess.run(['pdftotext', '-layout', pdf_path, out_path],
                       check=True, capture_output=True)
    except FileNotFoundError:
        sys.exit("ERROR: pdftotext not found.\n  macOS: brew install poppler\n  Ubuntu: sudo apt install poppler-utils")
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERROR converting {pdf_path}:\n{e.stderr.decode()}")


# ═══════════════════════════════════════════════════════════════════════════════
# PARSERS
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_layout_line(line, fmt):
    """
    Parse one layout-mode text line into a dict with keys:
      name, club, sex, ag, sec
    Returns None if the line doesn't look like a finisher row.
    fmt: '2026' or '2425'
    """
    m = SEX_RANK_RE.search(line)
    if not m:
        return None

    sex  = m.group(2)                  # 'M' or 'F'
    before = line[:m.start()].strip()  # everything before sex-rank
    after  = line[m.end():]            # everything after sex-rank

    # ── extract name and club from 'before' ───────────────────────────────
    # Split on 2+ consecutive spaces
    parts = [p for p in re.split(r'\s{2,}', before.strip()) if p.strip()]

    if fmt == '2026':
        # parts = [bib+pos, name, club?]  or  [bib, pos, name, club?]
        # name is the first all-letter token (not all digits/spaces)
        name_idx = next((i for i, p in enumerate(parts)
                         if re.search(r'[A-Za-z]', p)), None)
        if name_idx is None:
            return None
        name = parts[name_idx].strip()
        club = parts[name_idx + 1].strip() if name_idx + 1 < len(parts) else ''
    else:
        # parts = [rank, bib, name, club?]
        if len(parts) < 3:
            return None
        name = parts[2].strip()
        club = parts[3].strip() if len(parts) > 3 else ''

    # ── extract AG and time from 'after' ──────────────────────────────────
    after = after.strip()
    t_m = HMMSS_RE.search(after) or MMSS_RE.search(after)
    if not t_m:
        return None
    ag_raw = after[:t_m.start()].strip()
    ag     = normalize_ag(ag_raw, sex)
    sec    = time_to_sec(t_m.group())

    return {'name': name, 'club': club, 'sex': sex, 'ag': ag, 'sec': sec}


def parse_txt(txt_path, race, year):
    fmt = '2026' if year == 2026 else '2425'
    records = []
    cur_sex = None
    seen_header = False

    with open(txt_path, encoding='utf-8', errors='replace') as fh:
        lines = fh.readlines()

    for i, line in enumerate(lines):
        ls = line.strip()

        # Section headers
        if ls in ('Male', 'Female'):
            cur_sex = 'M' if ls == 'Male' else 'F'
            continue

        # Skip page headers (contain "Bib" / "Rank" but not a finisher)
        if re.search(r'\bBib\b|\bRank\b', line) and 'Name' in line:
            continue

        rec = _parse_layout_line(line, fmt)
        if rec and rec['sec'] and rec['sex']:
            records.append({
                'race': race,
                'name': rec['name'],
                'club': rec['club'],
                'sex':  rec['sex'],
                'ag':   rec['ag'],
                'sec':  rec['sec'],
            })

    # 2026: chip+gun both match; deduplicate by removing consecutive duplicates
    if fmt == '2026':
        deduped = []
        for r in records:
            if deduped and deduped[-1]['name'] == r['name'] and abs(deduped[-1]['sec'] - r['sec']) <= 120:
                continue   # skip gun time (same runner, within 2 min)
            deduped.append(r)
        records = deduped

    return records


def load_year(year, data_dir, tmp_dir):
    year_dir = os.path.join(data_dir, str(year))
    if not os.path.isdir(year_dir):
        sys.exit(f"ERROR: directory not found: {year_dir}")

    file_map = PDF_FILES.get(year)
    if not file_map:
        sys.exit(f"ERROR: no file mapping defined for year {year}. Add it to PDF_FILES.")

    all_records = []
    for race, fname in file_map.items():
        pdf_path = os.path.join(year_dir, fname)
        if not os.path.exists(pdf_path):
            print(f"  WARNING: {pdf_path} not found — skipping")
            continue
        txt_path = os.path.join(tmp_dir, f"{year}_{race}.txt")
        print(f"  Converting {year} {race}…", end=' ', flush=True)
        pdf_to_text(pdf_path, txt_path)
        recs = parse_txt(txt_path, race, year)
        print(f"{len(recs):,} finishers")
        all_records.extend(recs)

    return pd.DataFrame(all_records)


# ═══════════════════════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════════════════════

def race_stats(df, race):
    sub = df[df['race'] == race]
    if sub.empty:
        return {}
    m = sub[sub['sex'] == 'M']
    f = sub[sub['sex'] == 'F']
    return {
        'total':       len(sub),
        'male':        len(m),
        'female':      len(f),
        'pct_male':    round(100 * len(m) / len(sub)) if len(sub) else 0,
        'pct_female':  round(100 * len(f) / len(sub)) if len(sub) else 0,
        'fastest':     sub['sec'].min(),
        'fastest_m':   m['sec'].min() if len(m) else None,
        'fastest_f':   f['sec'].min() if len(f) else None,
        'median':      sub['sec'].median(),
        'median_m':    m['sec'].median() if len(m) else None,
        'median_f':    f['sec'].median() if len(f) else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CHART HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def fig_to_image(fig, width_cm=17):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white')
    buf.seek(0)
    plt.close(fig)
    img = Image(buf)
    img.drawWidth  = width_cm * cm
    img.drawHeight = width_cm * cm * (fig.get_figheight() / fig.get_figwidth())
    return img


def style_ax(ax, title='', xlabel='', ylabel='', grid_axis='y'):
    ax.set_title(title, fontsize=10, fontweight='bold', pad=6)
    if xlabel: ax.set_xlabel(xlabel, fontsize=9)
    if ylabel: ax.set_ylabel(ylabel, fontsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    if grid_axis:
        ax.grid(axis=grid_axis, alpha=0.25, linestyle='--')
    ax.tick_params(labelsize=8)


# ── Cover: stacked bar gender split ──────────────────────────────────────────
def chart_gender_split(df, year):
    fig, ax = plt.subplots(figsize=(7, 4))
    race_labels = ['Marathon', 'Half\nMarathon', '10K']
    for i, (race, label) in enumerate(zip(RACES, race_labels)):
        sub = df[df['race'] == race]
        m = len(sub[sub['sex'] == 'M'])
        f = len(sub[sub['sex'] == 'F'])
        total = m + f
        pct_m = round(100 * m / total) if total else 0
        pct_f = round(100 * f / total) if total else 0
        ax.bar(i, m, color=C_BLUE, width=0.5)
        ax.bar(i, f, bottom=m, color=C_PINK, width=0.5)
        # labels inside bars
        if m > 30:
            ax.text(i, m / 2, f"{m:,}\n({pct_m}%)", ha='center', va='center',
                    fontsize=8, color='white', fontweight='bold')
        if f > 30:
            ax.text(i, m + f / 2, f"{f:,}\n({pct_f}%)", ha='center', va='center',
                    fontsize=8, color='white', fontweight='bold')
    ax.set_xticks(range(3))
    ax.set_xticklabels(race_labels, fontsize=9)
    ax.set_ylabel('Finishers', fontsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    m_p = mpatches.Patch(color=C_BLUE, label='Male')
    f_p = mpatches.Patch(color=C_PINK, label='Female')
    ax.legend(handles=[m_p, f_p], fontsize=8, loc='upper right')
    fig.tight_layout()
    return fig_to_image(fig, width_cm=9)


# ── Finish time distribution (15-min buckets) ────────────────────────────────
def chart_time_distribution(df, race):
    sub = df[df['race'] == race]
    mins = sub['sec'] / 60

    # Choose bucket width and range based on race
    if race == 'Full':
        bucket = 15; lo = 135; hi = 480   # 2:15 to 8:00
    elif race == 'Half':
        bucket = 15; lo = 60;  hi = 270   # 1:00 to 4:30
    else:
        bucket = 5;  lo = 28;  hi = 130   # 0:28 to 2:10

    bins = np.arange(lo, hi + bucket, bucket)

    fig, ax = plt.subplots(figsize=(9, 3.5))
    m_vals, _ = np.histogram(sub[sub['sex'] == 'M']['sec'] / 60, bins=bins)
    f_vals, _ = np.histogram(sub[sub['sex'] == 'F']['sec'] / 60, bins=bins)

    x = bins[:-1]
    w = bucket * 0.85
    ax.bar(x, m_vals, width=w, align='edge', color=C_BLUE, alpha=0.85, label='Male')
    ax.bar(x, f_vals, width=w, align='edge', bottom=m_vals, color=C_PINK, alpha=0.85, label='Female')

    # x-tick labels as H:MM
    tick_pos = bins[::2]
    tick_lbl = [f"{int(t)//60}:{int(t)%60:02d}" for t in tick_pos]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lbl, rotation=45, ha='right', fontsize=7)

    m_p = mpatches.Patch(color=C_BLUE, alpha=0.85, label='Male')
    f_p = mpatches.Patch(color=C_PINK, alpha=0.85, label='Female')
    ax.legend(handles=[m_p, f_p], fontsize=8, loc='upper right')
    style_ax(ax, title='Finish Time Distribution (15-min buckets)',
             xlabel='Finish Time (chip)', ylabel='Finishers')
    fig.tight_layout()
    return fig_to_image(fig, width_cm=15)


# ── Age group count + median time charts (one sex) ───────────────────────────
def chart_ag_pair(df, race, sex):
    sub   = df[(df['race'] == race) & (df['sex'] == sex)]
    color = C_BLUE if sex == 'M' else C_PINK
    order = M_AG_ORDER if sex == 'M' else F_AG_ORDER
    ags   = [a for a in order if a in sub['ag'].values]

    counts  = [len(sub[sub['ag'] == a]) for a in ags]
    medians = [sub[sub['ag'] == a]['sec'].median() / 60 for a in ags]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2))
    x = np.arange(len(ags))

    ax1.bar(x, counts, color=color, alpha=0.85)
    ax1.set_xticks(x); ax1.set_xticklabels(ags, fontsize=7)
    style_ax(ax1, title=f"{'Male' if sex=='M' else 'Female'} Age Group Counts",
             ylabel='Finishers')

    ax2.bar(x, medians, color=color, alpha=0.85)
    ax2.set_xticks(x); ax2.set_xticklabels(ags, fontsize=7)
    style_ax(ax2, title=f"{'Male' if sex=='M' else 'Female'} Median Finish (mins)",
             ylabel='Median Time (min)')

    fig.tight_layout(pad=1.5)
    return fig_to_image(fig, width_cm=15)


# ── Club: affiliation rate stacked bars ──────────────────────────────────────
def chart_club_affiliation(df):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))

    race_labels = ['Marathon', 'Half Marathon', '10K']
    with_club  = []
    no_club    = []
    pcts       = []
    unique_cls = []

    for race in RACES:
        sub = df[df['race'] == race]
        wc  = (sub['club'].str.strip() != '').sum()
        with_club.append(wc)
        no_club.append(len(sub) - wc)
        pcts.append(round(100 * wc / len(sub)) if len(sub) else 0)
        unique_cls.append(sub[sub['club'].str.strip() != '']['club'].nunique())

    x = np.arange(3)
    w = 0.45
    # Green (with club) at bottom, grey (no club) stacked on top
    ax1.bar(x, with_club, w, color=C_GREEN,   label='With club')
    ax1.bar(x, no_club,   w, bottom=with_club, color='#CCCCCC', label='No club')
    for i, (pct, wc) in enumerate(zip(pcts, with_club)):
        ax1.text(i, wc / 2, f"{pct}%", ha='center', va='center',
                 fontsize=9, fontweight='bold', color='white')
    ax1.set_xticks(x); ax1.set_xticklabels(race_labels, fontsize=9)
    ax1.legend(fontsize=8)
    style_ax(ax1, title='Club Affiliation Rate', ylabel='Finishers')

    bar_colors = [C_GREEN, C_GOLD, C_BLUE]
    bars = ax2.bar(x, unique_cls, 0.5, color=bar_colors, alpha=0.9)
    for bar, val in zip(bars, unique_cls):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 str(val), ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax2.set_xticks(x); ax2.set_xticklabels(race_labels, fontsize=9)
    style_ax(ax2, title='Unique Clubs per Race', ylabel='Number of Clubs')

    fig.tight_layout()
    return fig_to_image(fig, width_cm=15)


# ── How many club rows fit on one page ───────────────────────────────────────
def _clubs_per_page(chart_w_cm=14, fig_w_in=9, row_h_in=0.42,
                    page_h_cm=29.7, margin_cm=2.0, header_cm=2.0):
    """Return the max number of club rows that keep the chart on a single page."""
    available_cm = page_h_cm - 2 * margin_cm - header_cm
    return max(10, int(available_cm * fig_w_in / (chart_w_cm * row_h_in)))


# ── Top clubs horizontal bar chart ───────────────────────────────────────────
def chart_top_clubs(df, race, n=None):
    sub = df[(df['race'] == race) & (df['club'].str.strip() != '')]
    if sub.empty:
        return None

    if n is None:
        n = _clubs_per_page()
    top = (sub.groupby('club').size()
              .sort_values(ascending=False)
              .head(n))
    clubs = top.index.tolist()[::-1]   # bottom-to-top

    m_counts = [len(sub[(sub['club'] == c) & (sub['sex'] == 'M')]) for c in clubs]
    f_counts = [len(sub[(sub['club'] == c) & (sub['sex'] == 'F')]) for c in clubs]

    fig, ax = plt.subplots(figsize=(9, max(4, len(clubs) * 0.42)))
    y = np.arange(len(clubs))
    ax.barh(y, m_counts, color=C_BLUE, alpha=0.85)
    ax.barh(y, f_counts, left=m_counts, color=C_PINK, alpha=0.85)

    totals = [m + f for m, f in zip(m_counts, f_counts)]
    for i, (m, f, tot) in enumerate(zip(m_counts, f_counts, totals)):
        if m > 0:
            ax.text(m / 2, i, f"M:{m}", ha='center', va='center',
                    fontsize=7, color='white', fontweight='bold')
        if f > 0:
            ax.text(m + f / 2, i, f"F:{f}", ha='center', va='center',
                    fontsize=7, color='white', fontweight='bold')
        ax.text(tot + 0.2, i, str(tot), va='center', fontsize=7.5)

    ax.set_yticks(y); ax.set_yticklabels(clubs, fontsize=8)
    style_ax(ax, title=f'Top Clubs — {race}', xlabel='Finishers', grid_axis='x')
    ax.spines['left'].set_visible(False)
    m_p = mpatches.Patch(color=C_BLUE, alpha=0.85, label='Male')
    f_p = mpatches.Patch(color=C_PINK, alpha=0.85, label='Female')
    ax.legend(handles=[m_p, f_p], fontsize=8, loc='lower right')
    fig.tight_layout()
    return fig_to_image(fig, width_cm=14)


# ── Combined top clubs ────────────────────────────────────────────────────────
def chart_top_clubs_combined(df, n=None):
    sub = df[df['club'].str.strip() != '']
    if sub.empty:
        return None

    if n is None:
        n = _clubs_per_page()
    top = (sub.groupby('club').size()
              .sort_values(ascending=False)
              .head(n))
    clubs  = top.index.tolist()[::-1]
    totals = [top[c] for c in clubs]

    fig, ax = plt.subplots(figsize=(9, max(4, len(clubs) * 0.35)))
    y = np.arange(len(clubs))
    ax.barh(y, totals, color=C_GREEN, alpha=0.85)
    for i, t in enumerate(totals):
        ax.text(t + 0.3, i, str(t), va='center', fontsize=7.5)

    ax.set_yticks(y); ax.set_yticklabels(clubs, fontsize=8)
    style_ax(ax, title='Top Clubs — Combined (All Races)',
             xlabel='Total Finishers (all races combined)', grid_axis='x')
    ax.spines['left'].set_visible(False)
    fig.tight_layout()
    return fig_to_image(fig, width_cm=14)


# ── Club age group heatmap ────────────────────────────────────────────────────
DECADE_MAP = {
    'M': '18-34', 'F': '18-34',
    'M35': '35-39', 'F35': '35-39',
    'M40': '40-44', 'F40': '40-44',
    'M45': '45-49', 'F45': '45-49',
    'M50': '50-54', 'F50': '50-54',
    'M55': '55-59', 'F55': '55-59',
    'M60': '60-64', 'F60': '60-64',
    'M65': '65-69', 'F65': '65-69',
    'M70': '70+',   'F70': '70+',
    'M75': '70+',   'F75': '70+',
    'M80': '70+',   'F80': '70+',
}
DECADES = ['18-34','35-39','40-44','45-49','50-54','55-59','60-64','65-69','70+']


def chart_age_group_heatmap(df, race, min_finishers=15):
    """Heatmap: qualifying clubs × age groups, values = finisher count."""
    sub = df[(df['race'] == race) & (df['club'].str.strip() != '')].copy()
    sub['decade'] = sub['ag'].map(DECADE_MAP)

    # Qualifying clubs sorted by total finishers desc
    counts = sub.groupby('club').size()
    qualifying = counts[counts >= min_finishers].sort_values(ascending=False)
    if qualifying.empty:
        return None

    clubs = qualifying.index.tolist()

    # Build count matrix
    matrix = pd.DataFrame(
        [[len(sub[(sub['club'] == c) & (sub['decade'] == d)]) for d in DECADES]
         for c in clubs],
        index=clubs, columns=DECADES
    )

    fig_h = max(3.5, len(clubs) * 0.38)
    fig, ax = plt.subplots(figsize=(11, fig_h))

    vmax = matrix.values.max()
    im = ax.imshow(matrix.values, aspect='auto', cmap='Greens',
                   vmin=0, vmax=max(vmax, 1))

    ax.set_xticks(range(len(DECADES)))
    ax.set_xticklabels(DECADES, rotation=40, ha='right', fontsize=8)
    ax.set_yticks(range(len(clubs)))
    ax.set_yticklabels(clubs, fontsize=8)

    # Annotate non-zero cells
    threshold = vmax * 0.55
    for i in range(len(clubs)):
        for j in range(len(DECADES)):
            val = matrix.iloc[i, j]
            if val > 0:
                tc = 'white' if val >= threshold else '#333333'
                ax.text(j, i, str(val), ha='center', va='center',
                        fontsize=7, color=tc, fontweight='bold' if val >= threshold else 'normal')

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.5, pad=0.02)
    cbar.ax.tick_params(labelsize=7)
    cbar.set_label('Finishers', fontsize=8)

    # Grid lines between cells
    ax.set_xticks(np.arange(-0.5, len(DECADES)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(clubs)), minor=True)
    ax.grid(which='minor', color='white', linewidth=0.8)
    ax.tick_params(which='minor', length=0)

    ax.set_title(
        f'{race} — Age Group Breakdown by Club  '
        f'(clubs with ≥ {min_finishers} finishers, sorted by total)',
        fontsize=10, fontweight='bold', pad=8
    )
    fig.tight_layout()
    return fig_to_image(fig, width_cm=15)


# ── Club age group heatmap — all races combined ───────────────────────────────
def chart_age_group_heatmap_overall(df, min_finishers=15):
    """Single heatmap combining all races: clubs × age groups, all finishers."""
    sub = df[df['club'].str.strip() != ''].copy()
    sub['decade'] = sub['ag'].map(DECADE_MAP)

    counts = sub.groupby('club').size()
    qualifying = counts[counts >= min_finishers].sort_values(ascending=False)
    if qualifying.empty:
        return None

    clubs = qualifying.index.tolist()
    matrix = pd.DataFrame(
        [[len(sub[(sub['club'] == c) & (sub['decade'] == d)]) for d in DECADES]
         for c in clubs],
        index=clubs, columns=DECADES
    )

    fig_h = max(3.5, len(clubs) * 0.38)
    fig, ax = plt.subplots(figsize=(11, fig_h))
    vmax = max(matrix.values.max(), 1)
    im = ax.imshow(matrix.values, aspect='auto', cmap='Greens', vmin=0, vmax=vmax)

    ax.set_xticks(range(len(DECADES)))
    ax.set_xticklabels(DECADES, rotation=40, ha='right', fontsize=8)
    ax.set_yticks(range(len(clubs)))
    ax.set_yticklabels(clubs, fontsize=8)

    threshold = vmax * 0.55
    for i in range(len(clubs)):
        for j in range(len(DECADES)):
            val = matrix.iloc[i, j]
            if val > 0:
                tc = 'white' if val >= threshold else '#333333'
                ax.text(j, i, str(val), ha='center', va='center', fontsize=7,
                        color=tc, fontweight='bold' if val >= threshold else 'normal')

    ax.set_xticks(np.arange(-0.5, len(DECADES)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(clubs)), minor=True)
    ax.grid(which='minor', color='white', linewidth=0.8)
    ax.tick_params(which='minor', length=0)
    cbar = fig.colorbar(im, ax=ax, shrink=0.5, pad=0.02)
    cbar.ax.tick_params(labelsize=7)
    cbar.set_label('Finishers', fontsize=8)
    ax.set_title(
        f'All Races Combined — Age Group Breakdown by Club  '
        f'(clubs with ≥ {min_finishers} total finishers)',
        fontsize=10, fontweight='bold', pad=8
    )
    fig.tight_layout()
    return fig_to_image(fig, width_cm=15)


# ── Club age group heatmap — split by gender ──────────────────────────────────
def _heatmap_ax(ax, matrix, clubs, title, cmap, vmax):
    """Draw a single heatmap onto an existing axes."""
    im = ax.imshow(matrix.values, aspect='auto', cmap=cmap, vmin=0, vmax=max(vmax, 1))
    ax.set_xticks(range(len(DECADES)))
    ax.set_xticklabels(DECADES, rotation=40, ha='right', fontsize=7)
    ax.set_yticks(range(len(clubs)))
    ax.set_yticklabels(clubs, fontsize=7)
    threshold = vmax * 0.55
    for i in range(len(clubs)):
        for j in range(len(DECADES)):
            val = matrix.iloc[i, j]
            if val > 0:
                tc = 'white' if val >= threshold else '#333333'
                ax.text(j, i, str(val), ha='center', va='center', fontsize=6.5,
                        color=tc, fontweight='bold' if val >= threshold else 'normal')
    ax.set_xticks(np.arange(-0.5, len(DECADES)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(clubs)), minor=True)
    ax.grid(which='minor', color='white', linewidth=0.8)
    ax.tick_params(which='minor', length=0)
    ax.set_title(title, fontsize=9, fontweight='bold', pad=6)
    return im


def chart_age_group_heatmap_by_gender(df, race, min_finishers=15):
    """Side-by-side Male / Female heatmaps for one race."""
    sub = df[(df['race'] == race) & (df['club'].str.strip() != '')].copy()
    sub['decade'] = sub['ag'].map(DECADE_MAP)

    # Clubs qualifying on total (M+F)
    counts = sub.groupby('club').size()
    qualifying = counts[counts >= min_finishers].sort_values(ascending=False)
    if qualifying.empty:
        return None
    clubs = qualifying.index.tolist()

    def make_matrix(sex):
        ag_cols = [f'M{d}' if d != '18-34' else 'M' for d in DECADES] if sex == 'M' \
             else [f'F{d}' if d != '18-34' else 'F' for d in DECADES]
        # Use decade label directly from DECADE_MAP
        s = sub[sub['sex'] == sex]
        return pd.DataFrame(
            [[len(s[(s['club'] == c) & (s['decade'] == d)]) for d in DECADES]
             for c in clubs],
            index=clubs, columns=DECADES
        )

    m_matrix = make_matrix('M')
    f_matrix = make_matrix('F')
    vmax = max(m_matrix.values.max(), f_matrix.values.max(), 1)

    fig_h = max(3.5, len(clubs) * 0.38)
    fig, (ax_m, ax_f) = plt.subplots(1, 2, figsize=(16, fig_h), sharey=True)

    im_m = _heatmap_ax(ax_m, m_matrix, clubs, f'{race} — Male', 'Blues', vmax)
    im_f = _heatmap_ax(ax_f, f_matrix, clubs, f'{race} — Female', 'RdPu', vmax)

    fig.colorbar(im_m, ax=ax_m, shrink=0.4, pad=0.02).ax.tick_params(labelsize=7)
    fig.colorbar(im_f, ax=ax_f, shrink=0.4, pad=0.02).ax.tick_params(labelsize=7)

    fig.suptitle(
        f'{race} — Age Group Breakdown by Club and Gender  '
        f'(clubs with ≥ {min_finishers} finishers)',
        fontsize=10, fontweight='bold', y=1.01
    )
    fig.tight_layout()
    return fig_to_image(fig, width_cm=17)


# ── Club team performance: avg finish time of top-5 finishers ────────────────
def chart_club_top5_avg(df, min_finishers=5):
    """
    For each race, show clubs with >= min_finishers athletes ranked by
    the average finish time of their 5 fastest finishers (ascending = fastest).
    """
    fig, axes = plt.subplots(1, 3, figsize=(16, 9), sharey=False)

    for ax, race in zip(axes, RACES):
        sub = df[(df['race'] == race) & (df['club'].str.strip() != '')]
        if sub.empty:
            ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes)
            continue

        # Clubs with enough finishers
        qualifying = sub.groupby('club').filter(lambda x: len(x) >= min_finishers)
        if qualifying.empty:
            ax.text(0.5, 0.5, f'No clubs with ≥{min_finishers} finishers',
                    ha='center', va='center', transform=ax.transAxes, fontsize=8)
            continue

        # Average of the 5 fastest per club
        results = (
            qualifying.groupby('club')['sec']
            .apply(lambda s: s.nsmallest(min_finishers).mean())
            .sort_values()
        )

        n = _clubs_per_page(chart_w_cm=14, row_h_in=0.38)
        results = results.head(n)
        clubs = results.index.tolist()[::-1]   # bottom-to-top
        avg_mins = [results[c] / 60 for c in clubs]

        y = np.arange(len(clubs))
        color = {
            'Full': C_GREEN, 'Half': C_BLUE, '10K': '#E67E22'
        }.get(race, C_BLUE)
        ax.barh(y, avg_mins, color=color, alpha=0.85)

        for i, (club, am) in enumerate(zip(clubs, avg_mins)):
            label = sec_to_hms(am * 60)
            ax.text(am + max(avg_mins) * 0.01, i, label,
                    va='center', fontsize=7.5)

        ax.set_yticks(y)
        ax.set_yticklabels(clubs, fontsize=8)
        ax.xaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"{int(v)//60}:{int(v)%60:02d}")
        )
        style_ax(ax, title=race,
                 xlabel=f'Avg time — top {min_finishers} finishers',
                 grid_axis='x')
        ax.spines['left'].set_visible(False)

    fig.suptitle(
        f'Club Team Performance — Average Top-{min_finishers} Finish Time\n'
        f'(clubs with ≥ {min_finishers} finishers, sorted fastest first)',
        fontsize=13, fontweight='bold', y=1.01
    )
    fig.tight_layout()
    return fig_to_image(fig, width_cm=17)


# ── Word cloud ────────────────────────────────────────────────────────────────
def _word_cloud_matplotlib(counts, n_clubs):
    """Matplotlib spiral word cloud — no external library needed."""
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_xlim(-1, 1); ax.set_ylim(-0.55, 0.55)
    ax.axis('off')

    max_count = max(counts.values())
    min_fs, max_fs = 7, 42
    palette = (plt.cm.tab20.colors + plt.cm.tab20b.colors + plt.cm.tab20c.colors)

    # Approximate char width/height in axes units for overlap check
    fig_w_pts = fig.get_figwidth() * fig.dpi
    fig_h_pts = fig.get_figheight() * fig.dpi
    ax_w = 2.0; ax_h = 1.1   # axes data range

    placed = []   # list of (x, y, half_w, half_h)

    def overlaps(x, y, hw, hh):
        for px, py, phw, phh in placed:
            if abs(x - px) < (hw + phw) * 1.1 and abs(y - py) < (hh + phh) * 1.2:
                return True
        return False

    rng = np.random.default_rng(42)
    step = 0; theta = 0
    for word, count in sorted(counts.items(), key=lambda x: -x[1]):
        fs   = min_fs + (max_fs - min_fs) * (count / max_count) ** 0.5
        col  = palette[hash(word) % len(palette)]
        # Approx half-extents in data coords
        chars = len(word)
        hw = chars * fs * 0.6 / fig_w_pts * ax_w / 2
        hh = fs * 1.4 / fig_h_pts * ax_h / 2

        placed_ok = False
        for attempt in range(600):
            r = 0.015 * attempt ** 0.6
            x = r * np.cos(theta)
            y = r * np.sin(theta) * 0.55
            theta += 0.35
            if abs(x) + hw < 0.98 and abs(y) + hh < 0.52:
                if not overlaps(x, y, hw, hh):
                    ax.text(x, y, word, ha='center', va='center',
                            fontsize=fs, color=col, alpha=0.88,
                            fontweight='bold' if count == max_count else 'normal')
                    placed.append((x, y, hw, hh))
                    placed_ok = True
                    break
        if not placed_ok:
            # Place without overlap check as last resort
            r = 0.5 + rng.random() * 0.45
            angle = rng.random() * 2 * np.pi
            x = r * np.cos(angle) * 0.9
            y = r * np.sin(angle) * 0.45
            if abs(x) < 0.97 and abs(y) < 0.5:
                ax.text(x, y, word, ha='center', va='center',
                        fontsize=max(fs * 0.6, min_fs), color=col, alpha=0.6)

    fig.tight_layout(pad=0.3)
    return fig_to_image(fig, width_cm=16)


def chart_word_cloud(df):
    """Word cloud using wordcloud library if installed, else matplotlib fallback."""
    sub    = df[df['club'].str.strip() != '']
    counts = sub['club'].str.strip().value_counts().to_dict()
    if not counts:
        return None
    n_clubs = len(counts)

    if HAS_WORDCLOUD:
        wc = WordCloud(
            width=2000, height=1000,
            background_color='white',
            colormap='tab20',
            max_font_size=180,
            min_font_size=7,
            prefer_horizontal=0.65,
            collocations=False,
            relative_scaling=0.5,
            margin=2,
        ).generate_from_frequencies(counts)
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.imshow(wc, interpolation='bilinear')
        ax.axis('off')
        # Title is shown as a ReportLab paragraph above — no duplicate title here
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        return fig_to_image(fig, width_cm=17)

    return _word_cloud_matplotlib(counts, n_clubs)


# ── Club Venn diagram ─────────────────────────────────────────────────────────
def chart_venn(df):
    sets = {}
    for race in RACES:
        sub = df[(df['race'] == race) & (df['club'].str.strip() != '')]
        sets[race] = set(sub['club'].str.strip().unique())

    full, half, tenk = sets['Full'], sets['Half'], sets['10K']
    all3     = full & half & tenk
    f_h_only = (full & half) - tenk
    f_k_only = (full & tenk) - half
    h_k_only = (half & tenk) - full
    f_only   = full  - half - tenk
    h_only   = half  - full - tenk
    k_only   = tenk  - full - half

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Clubs by Race — Venn Diagram', fontsize=12, fontweight='bold', pad=10)

    # Draw three ellipses
    ells = [
        mpatches.Ellipse((4.0, 4.8), 4.8, 3.2, angle=0,
                         facecolor=C_GREEN, alpha=0.25, edgecolor=C_GREEN, linewidth=2),
        mpatches.Ellipse((6.0, 4.8), 4.8, 3.2, angle=0,
                         facecolor=C_GOLD,  alpha=0.25, edgecolor=C_GOLD,  linewidth=2),
        mpatches.Ellipse((5.0, 3.2), 4.8, 3.2, angle=0,
                         facecolor=C_BLUE,  alpha=0.25, edgecolor=C_BLUE,  linewidth=2),
    ]
    for e in ells:
        ax.add_patch(e)

    # Region labels  (x, y, count, label)
    regions = [
        (2.2, 5.2, len(f_only),   'Mar only'),
        (7.8, 5.2, len(h_only),   'Half only'),
        (5.0, 1.6, len(k_only),   '10K only'),
        (4.7, 5.8, len(f_h_only), 'Mar+Half'),
        (3.5, 3.2, len(f_k_only), 'Mar+10K'),
        (6.5, 3.2, len(h_k_only), 'Half+10K'),
        (5.0, 4.2, len(all3),     'All 3 races'),
    ]
    for x, y, count, label in regions:
        fw = 'bold' if label == 'All 3 races' else 'normal'
        fs = 13 if label == 'All 3 races' else 10
        ax.text(x, y + 0.25, str(count), ha='center', va='center',
                fontsize=fs, fontweight='bold', color=C_DGREY)
        ax.text(x, y - 0.25, label, ha='center', va='center',
                fontsize=7, color=C_DGREY)

    # Legend
    leg = [
        mpatches.Patch(facecolor=C_GREEN, alpha=0.6, edgecolor=C_GREEN, label='Marathon'),
        mpatches.Patch(facecolor=C_GOLD,  alpha=0.6, edgecolor=C_GOLD,  label='Half Marathon'),
        mpatches.Patch(facecolor=C_BLUE,  alpha=0.6, edgecolor=C_BLUE,  label='10K'),
    ]
    ax.legend(handles=leg, fontsize=9, loc='upper right')
    fig.tight_layout()
    return fig_to_image(fig, width_cm=13)


# ═══════════════════════════════════════════════════════════════════════════════
# PDF REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def build_pdf(df, year, out_path, club_name=None):
    W, H = A4
    styles = getSampleStyleSheet()

    # Custom styles
    TITLE  = ParagraphStyle('TITLE', fontName='Helvetica-Bold', fontSize=26,
                             textColor=colors.HexColor(C_GREEN), spaceBefore=0,
                             spaceAfter=10, leading=32, alignment=TA_CENTER)
    SUB    = ParagraphStyle('SUB',   fontName='Helvetica', fontSize=13,
                             textColor=colors.HexColor(C_DGREY), spaceAfter=5, alignment=TA_CENTER)
    SEC    = ParagraphStyle('SEC',   fontName='Helvetica-Bold', fontSize=16,
                             textColor=colors.HexColor(C_GREEN), spaceAfter=4)
    SUBSEC = ParagraphStyle('SUBSEC',fontName='Helvetica-Bold', fontSize=11,
                             textColor=colors.HexColor(C_DGREY), spaceAfter=6)
    BODY   = ParagraphStyle('BODY',  fontName='Helvetica', fontSize=10,
                             spaceAfter=4, leading=14)
    BODYC  = ParagraphStyle('BODYC', fontName='Helvetica', fontSize=10,
                             spaceAfter=4, leading=14, alignment=TA_CENTER)
    BODYCB = ParagraphStyle('BODYCB',fontName='Helvetica-Bold', fontSize=10,
                             spaceAfter=4, leading=14, alignment=TA_CENTER)
    BODYR  = ParagraphStyle('BODYR', fontName='Helvetica', fontSize=10,
                             spaceAfter=4, leading=14, alignment=TA_RIGHT)
    FOOT   = ParagraphStyle('FOOT',  fontName='Helvetica', fontSize=8,
                             textColor=colors.grey, alignment=TA_CENTER)
    CT     = ParagraphStyle('CT',    fontName='Helvetica', fontSize=9,
                             textColor=colors.grey, alignment=TA_CENTER, spaceAfter=8)

    def hr(color=C_GREEN):
        return HRFlowable(width='100%', thickness=1.5,
                          color=colors.HexColor(color), spaceAfter=6)

    def table_style_green():
        return TableStyle([
            ('BACKGROUND',    (0,0),(-1,0), colors.HexColor(C_GREEN)),
            ('TEXTCOLOR',     (0,0),(-1,0), colors.white),
            ('FONTNAME',      (0,0),(-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0),(-1,-1), 9),
            ('ALIGN',         (0,0),(-1,-1), 'CENTER'),
            ('ALIGN',         (0,1),(0,-1), 'LEFT'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, colors.HexColor(C_LIGHT)]),
            ('GRID',          (0,0),(-1,-1), 0.3, colors.lightgrey),
            ('TOPPADDING',    (0,0),(-1,-1), 4),
            ('BOTTOMPADDING', (0,0),(-1,-1), 4),
            ('FONTNAME',      (0,-1),(-1,-1), 'Helvetica-Bold'),
        ])

    def colored(text, hex_color):
        return f'<font color="{hex_color}">{text}</font>'

    # ── Header/footer via page template ──────────────────────────────────────
    footer_text = f"Analog Devices Cork City Marathon {year} — Results Analysis"

    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(2*cm, 1.2*cm, footer_text)
        canvas.drawRightString(W - 2*cm, 1.2*cm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    story = []

    # ── PAGE 1: COVER ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(f'Cork City Marathon {year}', TITLE))
    story.append(Paragraph('Analog Devices Cork City Marathon', SUB))
    story.append(Paragraph('Race Results Analysis', SUB))
    story.append(Spacer(1, 1.2*cm))

    # Summary table
    hdr = ['Race', 'Finishers', 'Male', 'Female', 'Fastest', 'Median']
    rows = [hdr]
    totals = {'fin': 0, 'm': 0, 'f': 0}
    for race, label in zip(RACES, ['Marathon', 'Half Marathon', '10K']):
        st = race_stats(df, race)
        if not st:
            continue
        rows.append([
            label,
            f"{st['total']:,}",
            f"{st['male']:,}",
            f"{st['female']:,}",
            colored(sec_to_hms(st['fastest']), C_GOLD),
            sec_to_hms(st['median']),
        ])
        totals['fin'] += st['total']
        totals['m']   += st['male']
        totals['f']   += st['female']
    rows.append([
        Paragraph('<b>All Races</b>', BODY),
        Paragraph(f"<b>{totals['fin']:,}</b>", BODYCB),
        Paragraph(f"<b>{totals['m']:,}</b>", BODYCB),
        Paragraph(f"<b>{totals['f']:,}</b>", BODYCB),
        Paragraph('—', BODYCB),
        Paragraph('—', BODYCB),
    ])

    # Convert colored strings to centred Paragraphs
    parsed_rows = []
    for r in rows[1:]:
        parsed_rows.append([
            Paragraph(str(c), BODYC) if '<font' in str(c) else c
            for c in r
        ])

    sum_t = Table([hdr] + parsed_rows,
                  colWidths=[3.5*cm, 2.2*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm])
    sum_t.setStyle(table_style_green())
    story.append(sum_t)
    story.append(Spacer(1, 0.5*cm))

    # Gender split chart
    story.append(chart_gender_split(df, year))
    story.append(PageBreak())

    # ── PAGES 2-4: PER-RACE ───────────────────────────────────────────────────
    race_labels = {'Full': 'Marathon', 'Half': 'Half Marathon', '10K': '10K'}

    for race in RACES:
        sub = df[df['race'] == race]
        if sub.empty:
            continue
        st    = race_stats(df, race)
        label = race_labels[race]

        story.append(hr())
        story.append(Paragraph(f'{label} Results', SEC))
        story.append(Paragraph(f"{st['total']:,} finishers", SUBSEC))
        story.append(Spacer(1, 0.2*cm))

        # Two-column stats table
        m_str  = f"{st['male']:,} ({st['pct_male']}%)"
        f_str  = f"{st['female']:,} ({st['pct_female']}%)"
        left_data = [
            ['Total Finishers', f"{st['total']:,}"],
            ['Male Finishers',   Paragraph(colored(m_str, C_BLUE),  BODYR)],
            ['Female Finishers', Paragraph(colored(f_str, C_PINK),  BODYR)],
            ['Fastest Overall',  Paragraph(colored(sec_to_hms(st['fastest']), C_GOLD), BODYR)],
        ]
        right_data = [
            ['Fastest Male',   Paragraph(colored(sec_to_hms(st['fastest_m']), C_BLUE), BODYR)],
            ['Fastest Female', Paragraph(colored(sec_to_hms(st['fastest_f']), C_PINK), BODYR)],
            ['Median Overall', Paragraph(f"<b>{sec_to_hms(st['median'])}</b>", BODYR)],
            ['Median Male',    Paragraph(colored(sec_to_hms(st['median_m']), C_BLUE), BODYR)],
            ['Median Female',  Paragraph(colored(sec_to_hms(st['median_f']), C_PINK), BODYR)],
        ]

        ts_plain = TableStyle([
            ('FONTSIZE',      (0,0),(-1,-1), 9),
            ('ALIGN',         (1,0),(1,-1), 'RIGHT'),
            ('GRID',          (0,0),(-1,-1), 0.3, colors.lightgrey),
            ('ROWBACKGROUNDS',(0,0),(-1,-1), [colors.white, colors.HexColor(C_LIGHT)]),
            ('TOPPADDING',    (0,0),(-1,-1), 3),
            ('BOTTOMPADDING', (0,0),(-1,-1), 3),
        ])

        tl = Table(left_data,  colWidths=[3.8*cm, 2.8*cm])
        tr = Table(right_data, colWidths=[3.8*cm, 2.8*cm])
        tl.setStyle(ts_plain); tr.setStyle(ts_plain)

        pair = Table([[tl, Spacer(0.5*cm, 1), tr]], colWidths=[6.7*cm, 0.5*cm, 6.7*cm])
        pair.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story.append(pair)
        story.append(Spacer(1, 0.4*cm))

        # Finish time distribution
        story.append(chart_time_distribution(df, race))

        # Age group charts
        story.append(chart_ag_pair(df, race, 'M'))
        story.append(chart_ag_pair(df, race, 'F'))
        story.append(PageBreak())

    # ── CLUB ANALYSIS ─────────────────────────────────────────────────────────
    story.append(hr())
    story.append(Paragraph('Club Analysis', SEC))
    story.append(Paragraph('Club affiliation across all three races', SUBSEC))

    # Club summary table
    club_hdr = ['Race', 'Total Finishers', 'With Club', 'Affiliation Rate', 'Unique Clubs']
    club_rows = [club_hdr]
    tot_fin = tot_wc = 0
    unique_all = set()
    for race, label in zip(RACES, ['Marathon', 'Half Marathon', '10K']):
        sub = df[df['race'] == race]
        wc  = sub[sub['club'].str.strip() != '']
        pct = round(100 * len(wc) / len(sub)) if len(sub) else 0
        uc  = wc['club'].str.strip().nunique()
        club_rows.append([label, f"{len(sub):,}", f"{len(wc):,}", f"{pct}%", str(uc)])
        tot_fin += len(sub); tot_wc += len(wc)
        unique_all |= set(wc['club'].str.strip().unique())

    tot_pct = round(100 * tot_wc / tot_fin) if tot_fin else 0
    club_rows.append([
        Paragraph('<b>All Races</b>', BODY),
        Paragraph(f'<b>{tot_fin:,}</b>', BODYCB),
        Paragraph(f'<b>{tot_wc:,}</b>', BODYCB),
        Paragraph(f'<b>{tot_pct}%</b>', BODYCB),
        Paragraph(f'<b>{len(unique_all)} unique</b>', BODYCB),
    ])
    club_t = Table(club_rows, colWidths=[3.5*cm, 3*cm, 2.5*cm, 3*cm, 2.8*cm])
    club_ts = table_style_green()
    club_ts.add('ALIGN', (1, 1), (-1, -1), 'CENTER')   # numbers centred
    club_t.setStyle(club_ts)
    story.append(club_t)
    story.append(Spacer(1, 0.8*cm))

    # Affiliation charts
    story.append(chart_club_affiliation(df))
    story.append(Spacer(1, 0.4*cm))

    # Word cloud — inline on club analysis page
    n_clubs = df[df['club'].str.strip() != '']['club'].str.strip().nunique()
    story.append(Paragraph('Club Word Cloud', SUBSEC))
    story.append(Paragraph(
        f'All {n_clubs} clubs represented — size proportional to total finishers across all races',
        ParagraphStyle('WCS', fontName='Helvetica', fontSize=9,
                       textColor=colors.HexColor(C_DGREY), spaceAfter=4)))
    img = chart_word_cloud(df)
    if img:
        story.append(img)
    story.append(PageBreak())

    # ── VENN DIAGRAM (page 6) ─────────────────────────────────────────────────
    story.append(hr())
    story.append(Paragraph('Club Overlap by Race — Venn Diagram', SEC))

    sets = {}
    for race in RACES:
        sub = df[(df['race'] == race) & (df['club'].str.strip() != '')]
        sets[race] = set(sub['club'].str.strip().unique())
    full, half, tenk = sets['Full'], sets['Half'], sets['10K']
    all3 = full & half & tenk

    story.append(Paragraph(
        f"{len(all3)} clubs in all 3 races · "
        f"{len((full | half | tenk) - (full & half) - (full & tenk) - (half & tenk))} clubs in only one race",
        SUBSEC))

    img = chart_venn(df)
    if img: story.append(img)

    venn_data = [
        ['Region', 'Clubs', 'Meaning'],
        ['Marathon only',    str(len(full - half - tenk)),   'Clubs with finishers in marathon only'],
        ['Half only',        str(len(half - full - tenk)),   'Clubs with finishers in half marathon only'],
        ['10K only',         str(len(tenk - full - half)),   'Clubs with finishers in 10K only'],
        ['Marathon + Half',  str(len((full & half) - tenk)), 'Clubs in both, not 10K'],
        ['Marathon + 10K',   str(len((full & tenk) - half)), 'Clubs in both, not Half'],
        ['Half + 10K',       str(len((half & tenk) - full)), 'Clubs in both, not Marathon'],
        [Paragraph('<b>All 3 races</b>', BODY),
         Paragraph(f'<b>{len(all3)}</b>', BODYCB),
         Paragraph('<b>Clubs with finishers across all three races</b>', BODY)],
    ]
    venn_t = Table(venn_data, colWidths=[3.5*cm, 2*cm, 9.3*cm])
    venn_t.setStyle(table_style_green())
    story.append(Spacer(1, 0.3*cm))
    story.append(venn_t)
    story.append(PageBreak())

    # Club team performance
    story.append(hr())
    story.append(Paragraph('Club Team Performance', SEC))
    story.append(Paragraph(
        'Average finish time of the 5 fastest finishers, for clubs with at least 5 athletes. '
        'Sorted fastest first.', SUBSEC))
    story.append(Spacer(1, 0.2*cm))
    story.append(chart_club_top5_avg(df, min_finishers=5))
    story.append(PageBreak())

    # Club age group heatmap — all races combined (first)
    story.append(hr())
    story.append(Paragraph('Club Age Group Breakdown — All Races Combined', SEC))
    story.append(Paragraph(
        'Aggregated across Full Marathon, Half Marathon and 10K. '
        'Clubs with 15 or more total finishers.', SUBSEC))
    story.append(Spacer(1, 0.2*cm))
    img = chart_age_group_heatmap_overall(df, min_finishers=15)
    if img:
        story.append(img)
    story.append(PageBreak())

    # Club age group heatmaps — per race
    story.append(hr())
    story.append(Paragraph('Club Age Group Breakdown', SEC))
    story.append(Paragraph(
        'Age group distribution for clubs with 15 or more finishers. '
        'Darker cells indicate more finishers in that age group.',
        SUBSEC))
    story.append(Spacer(1, 0.2*cm))
    for race in RACES:
        img = chart_age_group_heatmap(df, race, min_finishers=15)
        if img:
            story.append(img)
            story.append(Spacer(1, 0.4*cm))
    story.append(PageBreak())

    # Club age group heatmaps — by gender
    story.append(hr())
    story.append(Paragraph('Club Age Group Breakdown by Gender', SEC))
    story.append(Paragraph(
        'Male and female age group distribution side by side, '
        'for clubs with 15 or more finishers per race.', SUBSEC))
    story.append(Spacer(1, 0.2*cm))
    for race in RACES:
        img = chart_age_group_heatmap_by_gender(df, race, min_finishers=15)
        if img:
            story.append(img)
            story.append(Spacer(1, 0.4*cm))
    story.append(PageBreak())

    # Top clubs — combined first, then per race
    story.append(Paragraph('Top Clubs — Combined (All Races)', SUBSEC))
    story.append(Spacer(1, 0.2*cm))
    img = chart_top_clubs_combined(df)
    if img: story.append(img)
    story.append(PageBreak())

    story.append(Paragraph('Top Clubs — Marathon', SUBSEC))
    story.append(Spacer(1, 0.2*cm))
    img = chart_top_clubs(df, 'Full')
    if img: story.append(img)
    story.append(PageBreak())

    story.append(Paragraph('Top Clubs — Half Marathon', SUBSEC))
    story.append(Spacer(1, 0.2*cm))
    img = chart_top_clubs(df, 'Half')
    if img: story.append(img)
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph('Top Clubs — 10K', SUBSEC))
    story.append(Spacer(1, 0.2*cm))
    img = chart_top_clubs(df, '10K')
    if img: story.append(img)
    story.append(PageBreak())

    # ── CLUB DEEP DIVE (optional, one or more clubs) ──────────────────────────
    if club_name:
        styles_dict = {
            'SEC': SEC, 'SUBSEC': SUBSEC, 'BODY': BODY,
            'BODYR': BODYR, 'BODYCB': BODYCB, 'CT': CT, 'hr': hr,
        }
        for name in club_name:
            matched = _find_club(df, name)
            if matched:
                print(f"  Adding club deep dive for: {matched}")
                build_club_section(df, matched, year, story, styles_dict)
            else:
                print(f"  WARNING: club '{name}' not found — skipped.")
                sample = sorted(df[df['club'].str.strip()!='']['club'].str.strip().unique())[:10]
                print(f"  Available clubs (sample): {sample}")

    # ── BUILD ─────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    print(f"\nReport saved: {out_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLUB DEEP DIVE
# ═══════════════════════════════════════════════════════════════════════════════

def _find_club(df, club_name):
    """Return the exact club string in df closest to club_name (case-insensitive)."""
    clubs = df[df['club'].str.strip() != '']['club'].str.strip().unique()
    # Exact match first
    for c in clubs:
        if c.lower() == club_name.lower():
            return c
    # Partial match
    matches = [c for c in clubs if club_name.lower() in c.lower()]
    if matches:
        return matches[0]
    return None


def chart_club_vs_field(df, race, club_name):
    """
    Finish time distribution: overall field in grey, club in green.
    Median lines for field and club. No athlete names.
    """
    sub      = df[df['race'] == race]
    club_sub = sub[sub['club'].str.strip() == club_name]
    if club_sub.empty:
        return None

    if race == 'Full':
        bucket, lo, hi = 15, 135, 480
    elif race == 'Half':
        bucket, lo, hi = 15,  60, 270
    else:
        bucket, lo, hi =  5,  28, 130

    bins = np.arange(lo, hi + bucket, bucket)
    field_vals, _ = np.histogram(sub['sec'] / 60, bins=bins)
    club_vals,  _ = np.histogram(club_sub['sec'] / 60, bins=bins)

    fig, ax = plt.subplots(figsize=(10, 3.5))
    x, w = bins[:-1], bucket * 0.85
    ax.bar(x, field_vals, width=w, align='edge', color='#CCCCCC', alpha=0.75, label='All finishers')
    ax.bar(x, club_vals,  width=w, align='edge', color=C_GREEN,   alpha=0.90, label=club_name)

    field_med = sub['sec'].median() / 60
    club_med  = club_sub['sec'].median() / 60
    ax.axvline(field_med, color='#999999', linestyle='--', linewidth=1.5, label='Overall median')
    ax.axvline(club_med,  color=C_GREEN,   linestyle='-',  linewidth=2,   label='Club median')

    tick_pos = bins[::2]
    tick_lbl = [f"{int(t)//60}:{int(t)%60:02d}" for t in tick_pos]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_lbl, rotation=45, ha='right', fontsize=7)
    ax.legend(fontsize=8)
    style_ax(ax, title=f'{race} — Finish Time: Club vs Field',
             xlabel='Finish Time (chip)', ylabel='Finishers')
    fig.tight_layout()
    return fig_to_image(fig, width_cm=15)


def chart_club_age_breakdown(df, club_name, race=None):
    """Age group bar chart for the club (M blue, F pink). No names."""
    sub = df[df['club'].str.strip() == club_name]
    if race:
        sub = sub[sub['race'] == race]
    if sub.empty:
        return None

    sub = sub.copy()
    sub['decade'] = sub['ag'].map(DECADE_MAP)

    fig, ax = plt.subplots(figsize=(9, 3.2))
    x = np.arange(len(DECADES))
    w = 0.35
    m_v = [len(sub[(sub['sex']=='M') & (sub['decade']==d)]) for d in DECADES]
    f_v = [len(sub[(sub['sex']=='F') & (sub['decade']==d)]) for d in DECADES]
    ax.bar(x - w/2, m_v, w, color=C_BLUE, alpha=0.85, label='Male')
    ax.bar(x + w/2, f_v, w, color=C_PINK, alpha=0.85, label='Female')
    for i, (m, f) in enumerate(zip(m_v, f_v)):
        if m: ax.text(i - w/2, m + 0.2, str(m), ha='center', va='bottom', fontsize=7)
        if f: ax.text(i + w/2, f + 0.2, str(f), ha='center', va='bottom', fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(DECADES, rotation=40, ha='right', fontsize=8)
    title = f'{race} — Age Group Breakdown' if race else 'Age Group Breakdown (All Races)'
    style_ax(ax, title=title, ylabel='Finishers')
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig_to_image(fig, width_cm=13)


def chart_club_gender_per_race(df, club_name):
    """Stacked bar: M/F split per race for the club."""
    sub = df[df['club'].str.strip() == club_name]
    fig, ax = plt.subplots(figsize=(5, 3.5))
    labels = ['Marathon', 'Half\nMarathon', '10K']
    for i, race in enumerate(RACES):
        r = sub[sub['race'] == race]
        m = len(r[r['sex']=='M']); f = len(r[r['sex']=='F'])
        total = m + f
        ax.bar(i, m, color=C_BLUE, width=0.5, alpha=0.85)
        ax.bar(i, f, bottom=m, color=C_PINK, width=0.5, alpha=0.85)
        if m: ax.text(i, m/2, f"M:{m}", ha='center', va='center',
                      fontsize=8, color='white', fontweight='bold')
        if f: ax.text(i, m + f/2, f"F:{f}", ha='center', va='center',
                      fontsize=8, color='white', fontweight='bold')
    ax.set_xticks(range(3)); ax.set_xticklabels(labels, fontsize=9)
    m_p = mpatches.Patch(color=C_BLUE, alpha=0.85, label='Male')
    f_p = mpatches.Patch(color=C_PINK, alpha=0.85, label='Female')
    ax.legend(handles=[m_p, f_p], fontsize=8)
    style_ax(ax, title='Finishers by Race and Gender', ylabel='Finishers')
    fig.tight_layout()
    return fig_to_image(fig, width_cm=7)


def build_club_section(df, club_name, year, story, styles):
    """Append club deep dive pages to story. No athlete names used anywhere."""
    SEC, SUBSEC, BODY, BODYR, BODYCB, BODYCB2, CT, HR = (
        styles['SEC'], styles['SUBSEC'], styles['BODY'],
        styles['BODYR'], styles['BODYCB'], styles['BODYCB'],
        styles['CT'], styles['hr']
    )

    sub = df[df['club'].str.strip() == club_name]
    if sub.empty:
        print(f"  WARNING: no finishers found for club '{club_name}'")
        return

    def ts_plain():
        return TableStyle([
            ('FONTSIZE',       (0,0),(-1,-1), 9),
            ('ALIGN',          (1,0),(1,-1), 'RIGHT'),
            ('GRID',           (0,0),(-1,-1), 0.3, colors.lightgrey),
            ('ROWBACKGROUNDS', (0,0),(-1,-1), [colors.white, colors.HexColor(C_LIGHT)]),
            ('TOPPADDING',     (0,0),(-1,-1), 3),
            ('BOTTOMPADDING',  (0,0),(-1,-1), 3),
        ])

    def tsg():
        return TableStyle([
            ('BACKGROUND',    (0,0),(-1,0), colors.HexColor(C_GREEN)),
            ('TEXTCOLOR',     (0,0),(-1,0), colors.white),
            ('FONTNAME',      (0,0),(-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',       (0,0),(-1,-1), 9),
            ('ALIGN',          (0,0),(-1,-1), 'CENTER'),
            ('ALIGN',          (0,1),(0,-1), 'LEFT'),
            ('ROWBACKGROUNDS', (0,1),(-1,-1), [colors.white, colors.HexColor(C_LIGHT)]),
            ('GRID',           (0,0),(-1,-1), 0.3, colors.lightgrey),
            ('TOPPADDING',     (0,0),(-1,-1), 4),
            ('BOTTOMPADDING',  (0,0),(-1,-1), 4),
            ('FONTNAME',       (0,-1),(-1,-1), 'Helvetica-Bold'),
        ])

    def colored(text, hex_color):
        return f'<font color="{hex_color}">{text}</font>'

    def club_rank(race, metric='count'):
        """Rank club among all clubs in a race by finisher count or median time."""
        r = df[(df['race'] == race) & (df['club'].str.strip() != '')]
        if metric == 'count':
            counts = r.groupby('club').size().sort_values(ascending=False)
            if club_name in counts.index:
                pos = list(counts.index).index(club_name) + 1
                return f"{pos} of {len(counts)}"
        elif metric == 'median':
            medians = r.groupby('club')['sec'].median().sort_values()
            if club_name in medians.index:
                pos = list(medians.index).index(club_name) + 1
                return f"{pos} of {len(medians)}"
        return '—'

    def percentile_in_field(race):
        """% of field the club median beats (higher = faster club)."""
        r = df[df['race'] == race]
        c = sub[sub['race'] == race]
        if r.empty or c.empty:
            return '—'
        club_med = c['sec'].median()
        pct = (r['sec'] > club_med).mean() * 100
        return f"{pct:.0f}%"

    # ── PAGE 1: Club Overview ─────────────────────────────────────────────────
    story.append(HR())
    story.append(Paragraph(f'Club Deep Dive: {club_name}', SEC))
    story.append(Paragraph(f'{year} Race Results — Anonymised Analysis', SUBSEC))
    story.append(Spacer(1, 0.3*cm))

    # Summary table
    hdr = ['Race', 'Finishers', 'Male', 'Female', 'Fastest', 'Median',
           'Rank (count)', 'Percentile']
    rows = [hdr]
    race_labels = {'Full': 'Marathon', 'Half': 'Half Marathon', '10K': '10K'}
    totals = {'fin': 0, 'm': 0, 'f': 0}
    for race in RACES:
        r = sub[sub['race'] == race]
        if r.empty:
            continue
        m_c = len(r[r['sex']=='M']); f_c = len(r[r['sex']=='F'])
        totals['fin'] += len(r); totals['m'] += m_c; totals['f'] += f_c
        rows.append([
            race_labels[race],
            str(len(r)), str(m_c), str(f_c),
            sec_to_hms(r['sec'].min()),   # plain string, colored via TableStyle below
            sec_to_hms(r['sec'].median()),
            club_rank(race, 'count'),
            percentile_in_field(race),
        ])
    rows.append([
        'Total',
        str(totals['fin']), str(totals['m']), str(totals['f']),
        '—', '—', '—', '—',
    ])

    # colWidths summing to 17cm
    t = Table(rows, colWidths=[3*cm, 2*cm, 1.7*cm, 1.7*cm, 2.1*cm, 2.1*cm, 2.5*cm, 1.9*cm])
    ts = tsg()
    ts.add('TEXTCOLOR', (4, 1), (4, -2), colors.HexColor(C_GOLD))   # fastest col gold
    ts.add('FONTNAME',  (0,-1), (-1,-1), 'Helvetica-Bold')
    t.setStyle(ts)
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    # Gender per race + overall age group side by side
    img_g   = chart_club_gender_per_race(df, club_name)
    img_age = chart_club_age_breakdown(df, club_name, race=None)
    if img_g and img_age:
        pair = Table([[img_g, '', img_age]],
                     colWidths=[7.2*cm, 0.4*cm, 9*cm])
        pair.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
        story.append(pair)

    # ── PAGES 2+: Per race ────────────────────────────────────────────────────
    for race in RACES:
        r = sub[sub['race'] == race]
        if r.empty:
            continue
        label = race_labels[race]
        m = r[r['sex']=='M']; f = r[r['sex']=='F']

        story.append(PageBreak())
        story.append(HR())
        story.append(Paragraph(f'{club_name} — {label}', SEC))
        story.append(Paragraph(f"{len(r)} finishers", SUBSEC))
        story.append(Spacer(1, 0.2*cm))

        # Stats tables (left + right, two columns to fit page width)
        m_str = f"{len(m)} ({round(100*len(m)/len(r))}%)" if len(r) else '—'
        f_str = f"{len(f)} ({round(100*len(f)/len(r))}%)" if len(r) else '—'
        left_data = [
            ['Total Finishers', str(len(r))],
            ['Male Finishers',   Paragraph(colored(m_str, C_BLUE), BODYR)],
            ['Female Finishers', Paragraph(colored(f_str, C_PINK), BODYR)],
            ['Fastest Overall',  Paragraph(colored(sec_to_hms(r['sec'].min()), C_GOLD), BODYR)],
        ]
        right_data = [
            ['Fastest Male',          Paragraph(colored(sec_to_hms(m['sec'].min() if len(m) else None), C_BLUE), BODYR)],
            ['Fastest Female',        Paragraph(colored(sec_to_hms(f['sec'].min() if len(f) else None), C_PINK), BODYR)],
            ['Median Overall',        Paragraph(f"<b>{sec_to_hms(r['sec'].median())}</b>", BODYR)],
            ['Median Male',           Paragraph(colored(sec_to_hms(m['sec'].median() if len(m) else None), C_BLUE), BODYR)],
            ['Median Female',         Paragraph(colored(sec_to_hms(f['sec'].median() if len(f) else None), C_PINK), BODYR)],
            ['Rank (by count)',       club_rank(race, 'count')],
            ['Rank (by median time)', club_rank(race, 'median')],
            ['Field percentile',      percentile_in_field(race)],
        ]

        tl = Table(left_data,  colWidths=[4.2*cm, 4*cm])
        tr = Table(right_data, colWidths=[4.2*cm, 4*cm])
        for t in [tl, tr]:
            t.setStyle(ts_plain())

        pair = Table([[tl, '', tr]],
                     colWidths=[8.2*cm, 0.6*cm, 8.2*cm])
        pair.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
        story.append(pair)
        story.append(Spacer(1, 0.4*cm))

        # Finish time vs field
        img = chart_club_vs_field(df, race, club_name)
        if img:
            story.append(img)
            story.append(Spacer(1, 0.3*cm))

        # Age group breakdown for this race
        img = chart_club_age_breakdown(df, club_name, race=race)
        if img:
            story.append(img)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description='Generate a single-year Cork City Marathon analysis PDF.')
    ap.add_argument('--year', type=int, required=True,
                    help='Race year, e.g. 2026')
    ap.add_argument('--data', default='data/cork',
                    help='Base data directory containing year sub-folders (default: data/cork)')
    ap.add_argument('--out', default=None,
                    help='Output PDF path (default: report_charts/cork_marathon_<year>_single.pdf)')
    ap.add_argument('--club', nargs='+', default=None,
                    help='One or more club names for deep dive sections, '
                         'e.g. --club "Togher A.C." "Eagle A.C."')
    args = ap.parse_args()

    out = args.out or f'report_charts/cork_marathon_{args.year}_single.pdf'
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        print(f"Loading {args.year} data from '{args.data}'…")
        df = load_year(args.year, args.data, tmp)

    if df.empty:
        sys.exit("ERROR: No records parsed. Check PDF files exist and are readable.")

    print(f"\nParsed {len(df):,} total finisher records.")
    print(df.groupby(['race','sex']).size().unstack(fill_value=0).to_string())

    print("\nBuilding charts and PDF…")
    build_pdf(df, args.year, out, club_name=args.club)


if __name__ == '__main__':
    main()
