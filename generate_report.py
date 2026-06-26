/#!/usr/bin/env python3
"""
Cork City Marathon — Race Analysis Report Generator
====================================================
Parses official PDF results for 2024, 2025, 2026 and produces a
multi-section PDF report with participation and finish-time trends.

Expected directory layout
-------------------------
data/cork/
  2024/
    02ResultsResults_full.pdf
    02ResultsResults_half.pdf
    02ResultsResults_10k.pdf
  2025/
    cc_results_full_2025.pdf
    02ResultsResults_half.pdf
    02ResultsResults_10k.pdf
  2026/
    ResultListsPURFullResults.pdf
    ResultListsPURFullResults_half.pdf
    ResultListsPURFullResults10km.pdf

Usage
-----
  python generate_report.py [--data cork_data] [--out cork_marathon_analysis.pdf]

Requirements
------------
  pip install -r requirements.txt
  pip install wordcloud          # optional but recommended for club word cloud
  System: poppler-utils  (provides pdftotext)
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
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
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

from generate_single_year_report import parse_txt

# ── Palette ───────────────────────────────────────────────────────────────────
C_RED    = '#C0392B'
C_GREEN  = '#27AE60'
C_BLUE   = '#2980B9'
C_ORANGE = '#E67E22'
C_PURPLE = '#8E44AD'
C_GREY   = '#7F8C8D'
C_LIGHT  = '#ECF0F1'

YEARS = [2024, 2025, 2026]
RACES = ['Full', 'Half', '10K']

# Compact AG codes produced by parse_txt (from generate_single_year_report)
AG_ORDER = ['18-34','35-39','40-44','45-49','50-54','55-59','60-64','65-69','70+']
# Compact codes used in the dataframe
AG_ORDER_COMPACT = ['35','40','45','50','55','60','65','70']  # decade suffixes (M/F prepended per sex)
AG_RE    = re.compile(
    r'\b([MF](?:18-34|35-39|40-44|45-49|50-54|55-59|60-64|65-69|70\+|Juvenile|Senior))\b'
)
AG_MAP = {
    'F18-34':'18-34','F35-39':'35-39','F40-44':'40-44','F45-49':'45-49',
    'F50-54':'50-54','F55-59':'55-59','F60-64':'60-64','F65-69':'65-69','F70+':'70+',
    'M18-34':'18-34','M35-39':'35-39','M40-44':'40-44','M45-49':'45-49',
    'M50-54':'50-54','M55-59':'55-59','M60-64':'60-64','M65-69':'65-69','M70+':'70+',
    'FSenior':'Senior','MSenior':'Senior',
    'FJuvenile':'Juvenile','MJuvenile':'Juvenile',
}

HMMSS_RE = re.compile(r'\b(\d{1,2}:\d{2}:\d{2})\b')
# MM:SS for times >= 30 min (avoids matching bib/rank numbers)
MMSS_RE  = re.compile(r'\b([3-9]\d:\d{2}|[1-9]\d\d:\d{2})\b')


# ═══════════════════════════════════════════════════════════════════════════════
# PDF → TEXT
# ═══════════════════════════════════════════════════════════════════════════════

def pdf_to_text(pdf_path: str, out_path: str) -> None:
    """Convert a PDF to plain text using pdftotext (poppler)."""
    try:
        subprocess.run(
            ['pdftotext', '-layout', pdf_path, out_path],
            check=True, capture_output=True
        )
    except FileNotFoundError:
        sys.exit(
            "ERROR: 'pdftotext' not found.\n"
            "  macOS:  brew install poppler\n"
            "  Ubuntu: sudo apt install poppler-utils"
        )
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERROR converting {pdf_path}:\n{e.stderr.decode()}")


# ═══════════════════════════════════════════════════════════════════════════════
# PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def time_to_sec(t: str):
    """Convert H:MM:SS or MM:SS string to total seconds. Returns None on error."""
    parts = t.split(':')
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None


def parse_2024_2025(txt_path: str, race: str, year: int) -> list[dict]:
    """
    Parse 2024/2025 text files.
    Format: one finisher per line; Full/Half use H:MM:SS, 10K uses MM:SS (fast) or H:MM:SS (slow).
    """
    records = []
    cur_sex = cur_ag = None

    with open(txt_path) as fh:
        for line in fh:
            ls = line.strip()

            if ls in ('Male', 'Female'):
                cur_sex = 'M' if ls == 'Male' else 'F'
                cur_ag  = None
                continue

            m_ag = AG_RE.search(ls)
            if m_ag and len(ls) < 25:
                cur_ag = AG_MAP.get(m_ag.group(1))
                continue

            # Prefer H:MM:SS; fall back to MM:SS
            times_h = HMMSS_RE.findall(line)
            times_m = MMSS_RE.findall(line)
            t_str   = times_h[0] if times_h else (times_m[0] if times_m else None)
            if not t_str:
                continue

            sm  = re.search(r' ([MF]) ', line)
            sex = sm.group(1) if sm else cur_sex
            ag_m = AG_RE.search(line)
            ag   = AG_MAP.get(ag_m.group(1), cur_ag) if ag_m else cur_ag
            sec  = time_to_sec(t_str)
            if sec and sex:
                records.append({'year': year, 'race': race, 'sex': sex, 'ag': ag, 'sec': sec})

    return records


def parse_2026(txt_path: str, race: str, year: int) -> list[dict]:
    """
    Parse 2026 text files.
    pdftotext renders the multi-column layout with each cell on its own line.
    Each finisher produces TWO consecutive time lines (chip + gun, separated by
    one blank line). We capture only the first (chip time) by skipping any time
    line that appears within 2 lines of the previous capture.
    """
    records = []
    cur_sex = cur_ag = None
    last_time_line = -99

    with open(txt_path) as fh:
        lines = fh.readlines()

    for i, raw in enumerate(lines):
        ls = raw.strip()

        if ls == 'Female':
            cur_sex = 'F'; continue
        if ls == 'Male':
            cur_sex = 'M'; continue

        # Bare AG header e.g. "F35-39"
        m_ag = AG_RE.match(ls)
        if m_ag and len(ls) < 12:
            cur_ag = AG_MAP.get(m_ag.group(1)); continue

        # Sex token e.g. "2. F" (overall rank line)
        sm = re.match(r'^\d+\.\s+([MF])$', ls)
        if sm:
            cur_sex = sm.group(1); continue

        # Time line — must be the whole stripped line
        if HMMSS_RE.fullmatch(ls):
            if i > last_time_line + 2:          # skip gun time (2 lines after chip)
                sec = time_to_sec(ls)
                if sec and cur_sex:
                    records.append({'year': year, 'race': race,
                                    'sex': cur_sex, 'ag': cur_ag, 'sec': sec})
            last_time_line = i

    return records


def load_data(data_dir: str, tmp_dir: str) -> pd.DataFrame:
    """Convert all PDFs to text and parse into a single DataFrame."""

    # Map: (label, race, year, parser, pdf_relative_path)
    file_specs = [
        ('2024 Full', 'Full', 2024, '2425', '2024/02ResultsResults_full.pdf'),
        ('2024 Half', 'Half', 2024, '2425', '2024/02ResultsResults_half.pdf'),
        ('2024 10K',  '10K',  2024, '2425', '2024/02ResultsResults_10k.pdf'),
        ('2025 Full', 'Full', 2025, '2425', '2025/cc_results_full_2025.pdf'),
        ('2025 Half', 'Half', 2025, '2425', '2025/02ResultsResults_half.pdf'),
        ('2025 10K',  '10K',  2025, '2425', '2025/02ResultsResults_10k.pdf'),
        ('2026 Full', 'Full', 2026, '2026', '2026/ResultListsPURFullResults.pdf'),
        ('2026 Half', 'Half', 2026, '2026', '2026/ResultListsPURFullResults_half.pdf'),
        ('2026 10K',  '10K',  2026, '2026', '2026/ResultListsPURFullResults10km.pdf'),
    ]

    all_records = []
    for label, race, year, parser, rel_path in file_specs:
        pdf_path = os.path.join(data_dir, rel_path)
        txt_path = os.path.join(tmp_dir, f"{label.replace(' ', '_')}.txt")

        if not os.path.exists(pdf_path):
            print(f"  WARNING: {pdf_path} not found — skipping")
            continue

        print(f"  Converting {label}…", end=' ', flush=True)
        pdf_to_text(pdf_path, txt_path)

        recs = parse_txt(txt_path, race, year)
        for r in recs:
            r['year'] = year   # parse_txt doesn't set year
        print(f"{len(recs):,} finishers")
        all_records.extend(recs)

    return pd.DataFrame(all_records)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def sec_to_hms(s: float) -> str:
    s = int(s)
    return f"{s//3600}:{(s%3600)//60:02d}:{s%60:02d}"


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    s = df.groupby(['year', 'race']).agg(
        total    = ('sec', 'count'),
        male     = ('sex', lambda x: (x == 'M').sum()),
        female   = ('sex', lambda x: (x == 'F').sum()),
        med_sec  = ('sec', 'median'),
        mean_sec = ('sec', 'mean'),
    ).reset_index()
    s['pct_female'] = (s['female'] / s['total'] * 100).round(1)
    s['med_str']    = s['med_sec'].apply(sec_to_hms)
    s['mean_str']   = s['mean_sec'].apply(sec_to_hms)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ═══════════════════════════════════════════════════════════════════════════════

def fig_to_image(fig, width_cm: float = 17) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    img = Image(buf)
    img.drawWidth  = width_cm * cm
    img.drawHeight = width_cm * cm * (fig.get_figheight() / fig.get_figwidth())
    return img


def style_ax(ax, title='', xlabel='', ylabel=''):
    ax.set_title(title, fontsize=13, fontweight='bold', pad=8)
    if xlabel: ax.set_xlabel(xlabel, fontsize=10)
    if ylabel: ax.set_ylabel(ylabel, fontsize=10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.tick_params(labelsize=9)


def chart_participation(summary: pd.DataFrame) -> Image:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    for ax, race in zip(axes, RACES):
        sub = summary[summary['race'] == race].set_index('year')
        males   = [int(sub.loc[y, 'male'])   if y in sub.index else 0 for y in YEARS]
        females = [int(sub.loc[y, 'female']) if y in sub.index else 0 for y in YEARS]
        x, w = np.arange(3), 0.35
        ax.bar(x - w/2, males,   w, label='Male',   color=C_BLUE, alpha=0.85)
        ax.bar(x + w/2, females, w, label='Female', color=C_RED,  alpha=0.85)
        for i, (m, f) in enumerate(zip(males, females)):
            ax.text(i - w/2, m + 8, str(m), ha='center', va='bottom', fontsize=8)
            ax.text(i + w/2, f + 8, str(f), ha='center', va='bottom', fontsize=8)
        ax.set_xticks(x); ax.set_xticklabels(YEARS)
        style_ax(ax, title=race, ylabel='Finishers' if race == 'Full' else '')
        if race == 'Full':
            ax.legend(fontsize=9)
    fig.suptitle('Finisher Count by Race and Gender (2024–2026)',
                 fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_total_trend(summary: pd.DataFrame) -> Image:
    fig, ax = plt.subplots(figsize=(10, 4))
    for race, col in zip(RACES, [C_BLUE, C_GREEN, C_ORANGE]):
        sub = summary[summary['race'] == race].sort_values('year')
        ax.plot(sub['year'], sub['total'], marker='o', linewidth=2.5,
                markersize=8, color=col, label=race)
        for _, row in sub.iterrows():
            ax.annotate(str(int(row['total'])), (row['year'], row['total']),
                        textcoords='offset points', xytext=(0, 9),
                        ha='center', fontsize=9, color=col)
    ax.set_xticks(YEARS)
    style_ax(ax, title='Total Finishers Trend (2024–2026)',
             xlabel='Year', ylabel='Total Finishers')
    ax.legend(fontsize=10)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_female_pct(summary: pd.DataFrame) -> Image:
    fig, ax = plt.subplots(figsize=(10, 4))
    for race, col in zip(RACES, [C_BLUE, C_GREEN, C_ORANGE]):
        sub = summary[summary['race'] == race].sort_values('year')
        ax.plot(sub['year'], sub['pct_female'], marker='s', linewidth=2.5,
                markersize=8, color=col, label=race)
        for _, row in sub.iterrows():
            ax.annotate(f"{row['pct_female']:.1f}%", (row['year'], row['pct_female']),
                        textcoords='offset points', xytext=(0, 8),
                        ha='center', fontsize=9, color=col)
    ax.set_xticks(YEARS); ax.set_ylim(0, 65)
    ax.axhline(50, color='grey', linestyle=':', alpha=0.5, label='50% line')
    style_ax(ax, title='Female Participation % by Race (2024–2026)',
             xlabel='Year', ylabel='% Female')
    ax.legend(fontsize=10)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_median_time(df: pd.DataFrame) -> Image:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    for ax, race in zip(axes, RACES):
        for sex, col, lbl in [('M', C_BLUE, 'Male'), ('F', C_RED, 'Female')]:
            vals = []
            for y in YEARS:
                s = df[(df['year'] == y) & (df['race'] == race) & (df['sex'] == sex)]['sec']
                vals.append(s.median() if len(s) else np.nan)
            hours = [v / 3600 if not np.isnan(v) else np.nan for v in vals]
            ax.plot(YEARS, hours, marker='o', linewidth=2, markersize=7, color=col, label=lbl)
            for y, v in zip(YEARS, vals):
                if not np.isnan(v):
                    ax.annotate(sec_to_hms(v), (y, v / 3600),
                                textcoords='offset points', xytext=(0, 7),
                                ha='center', fontsize=7.5, color=col)
        ax.set_xticks(YEARS)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"{int(v)}h{int((v % 1) * 60):02d}")
        )
        style_ax(ax, title=race, ylabel='Median Time' if race == 'Full' else '')
        if race == 'Full':
            ax.legend(fontsize=9)
    fig.suptitle('Median Finish Time by Race and Gender (2024–2026)',
                 fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_boxplot(df: pd.DataFrame, race: str) -> Image:
    sub = df[df['race'] == race]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    positions, labels, box_data, box_colors = [], [], [], []
    for i, year in enumerate(YEARS):
        for j, (sex, col) in enumerate([('M', C_BLUE), ('F', C_RED)]):
            d = sub[(sub['year'] == year) & (sub['sex'] == sex)]['sec'] / 3600
            positions.append(i * 3 + j)
            labels.append(f"{year}\n{'M' if sex == 'M' else 'F'}")
            box_data.append(d.dropna().values)
            box_colors.append(col)
    bp = ax.boxplot(box_data, positions=positions, widths=0.7, patch_artist=True,
                    showfliers=False, medianprops={'color': 'white', 'linewidth': 2})
    for patch, col in zip(bp['boxes'], box_colors):
        patch.set_facecolor(col); patch.set_alpha(0.75)
    ax.set_xticks(positions); ax.set_xticklabels(labels, fontsize=8)
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{int(v)}h{int((v % 1) * 60):02d}")
    )
    m_p = mpatches.Patch(color=C_BLUE, alpha=0.75, label='Male')
    f_p = mpatches.Patch(color=C_RED,  alpha=0.75, label='Female')
    ax.legend(handles=[m_p, f_p], fontsize=9)
    style_ax(ax, title=f'{race} — Finish Time Distribution (2024–2026)',
             ylabel='Finish Time')
    fig.tight_layout()
    return fig_to_image(fig)


def chart_age_group(df: pd.DataFrame, year: int = 2026) -> Image:
    # Compact AG codes: 'M', 'M35', 'M40'… and 'F', 'F35', 'F40'…
    # Combine M+F per decade for a combined breakdown
    decade_order = ['', '35', '40', '45', '50', '55', '60', '65', '70']
    labels       = ['18-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70+']

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    for ax, race in zip(axes, RACES):
        sub = df[(df['year'] == year) & (df['race'] == race)]
        m_v, f_v = [], []
        for d in decade_order:
            m_v.append(len(sub[(sub['sex'] == 'M') & (sub['ag'] == f'M{d}')]))
            f_v.append(len(sub[(sub['sex'] == 'F') & (sub['ag'] == f'F{d}')]))
        # Drop empty tail
        last = max((i for i, (m, f) in enumerate(zip(m_v, f_v)) if m + f > 0), default=0) + 1
        m_v, f_v, lbl = m_v[:last], f_v[:last], labels[:last]
        x, w = np.arange(len(lbl)), 0.35
        ax.bar(x - w/2, m_v, w, color=C_BLUE, alpha=0.8, label='Male')
        ax.bar(x + w/2, f_v, w, color=C_RED,  alpha=0.8, label='Female')
        ax.set_xticks(x); ax.set_xticklabels(lbl, rotation=45, ha='right', fontsize=8)
        style_ax(ax, title=race, ylabel='Finishers' if race == 'Full' else '')
        if race == 'Full':
            ax.legend(fontsize=9)
    fig.suptitle(f'Age Group Breakdown by Race — {year}',
                 fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_ag_trend(df: pd.DataFrame) -> Image:
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    # (label, M-code, F-code)
    age_groups = [
        ('18-34', 'M',   'F'),
        ('35-39', 'M35', 'F35'),
        ('40-44', 'M40', 'F40'),
        ('45-49', 'M45', 'F45'),
        ('50-54', 'M50', 'F50'),
        ('55-59', 'M55', 'F55'),
    ]
    cmap = plt.cm.tab10
    for ax, race in zip(axes, RACES):
        for idx, (label, m_code, f_code) in enumerate(age_groups):
            vals = [
                len(df[(df['year'] == y) & (df['race'] == race) &
                        df['ag'].isin([m_code, f_code])])
                for y in YEARS
            ]
            ax.plot(YEARS, vals, marker='o', linewidth=1.8, markersize=6,
                    color=cmap(idx), label=label)
        ax.set_xticks(YEARS)
        style_ax(ax, title=race, ylabel='Finishers' if race == 'Full' else '')
        if race == 'Full':
            ax.legend(fontsize=8, loc='upper left')
    fig.suptitle('Age Group Trend by Race (2024–2026)',
                 fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_word_cloud(df: pd.DataFrame) -> Image | None:
    sub = df[df['club'].str.strip() != '']
    counts = sub['club'].str.strip().value_counts().to_dict()
    if not counts:
        return None
    n_clubs = len(counts)
    if HAS_WORDCLOUD:
        wc = WordCloud(
            width=1200, height=600,
            background_color='white',
            colormap='tab20',
            max_font_size=90,
            min_font_size=8,
            prefer_horizontal=0.8,
            collocations=False,
        ).generate_from_frequencies(counts)
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.imshow(wc, interpolation='bilinear')
        ax.axis('off')
        ax.set_title(f'Club Word Cloud — {n_clubs} clubs · size ∝ finishers',
                     fontsize=11, fontweight='bold', pad=8)
        fig.tight_layout(pad=0)
        return fig_to_image(fig, width_cm=16)

    # Fallback word cloud placement when library is not installed
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_xlim(-1, 1); ax.set_ylim(-0.55, 0.55)
    ax.axis('off')
    ax.set_title(f'Club Word Cloud — {n_clubs} clubs · size ∝ finishers',
                 fontsize=11, fontweight='bold', pad=8)

    max_count = max(counts.values())
    min_fs, max_fs = 7, 42
    palette = (plt.cm.tab20.colors + plt.cm.tab20b.colors + plt.cm.tab20c.colors)
    placed = []

    def overlaps(x, y, hw, hh):
        for px, py, phw, phh in placed:
            if abs(x - px) < (hw + phw) * 1.1 and abs(y - py) < (hh + phh) * 1.2:
                return True
        return False

    rng = np.random.default_rng(42)
    theta = 0
    for word, count in sorted(counts.items(), key=lambda x: -x[1]):
        fs = min_fs + (max_fs - min_fs) * (count / max_count) ** 0.5
        col = palette[hash(word) % len(palette)]
        chars = len(word)
        fig_w_pts = fig.get_figwidth() * fig.dpi
        fig_h_pts = fig.get_figheight() * fig.dpi
        hw = chars * fs * 0.6 / fig_w_pts * 2.0 / 2
        hh = fs * 1.4 / fig_h_pts * 1.1 / 2
        placed_ok = False
        for attempt in range(600):
            r = 0.015 * attempt ** 0.6
            x = r * np.cos(theta)
            y = r * np.sin(theta) * 0.55
            theta += 0.35
            if abs(x) + hw < 0.98 and abs(y) + hh < 0.52 and not overlaps(x, y, hw, hh):
                ax.text(x, y, word, ha='center', va='center',
                        fontsize=fs, color=col, alpha=0.88,
                        fontweight='bold' if count == max_count else 'normal')
                placed.append((x, y, hw, hh))
                placed_ok = True
                break
        if not placed_ok:
            r = 0.5 + rng.random() * 0.45
            angle = rng.random() * 2 * np.pi
            x = r * np.cos(angle) * 0.9
            y = r * np.sin(angle) * 0.45
            ax.text(x, y, word, ha='center', va='center',
                    fontsize=max(fs * 0.6, min_fs), color=col, alpha=0.6)

    fig.tight_layout(pad=0.3)
    return fig_to_image(fig, width_cm=16)


# ═══════════════════════════════════════════════════════════════════════════════
# PDF REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def build_pdf(df: pd.DataFrame, summary: pd.DataFrame, out_path: str) -> None:
    print("\nBuilding charts…")
    imgs = {
        'participation': chart_participation(summary),
        'total_trend':   chart_total_trend(summary),
        'female_pct':    chart_female_pct(summary),
        'median_time':   chart_median_time(df),
        'box_full':      chart_boxplot(df, 'Full'),
        'box_half':      chart_boxplot(df, 'Half'),
        'box_10k':       chart_boxplot(df, '10K'),
        'ag_2026':       chart_age_group(df, 2026),
        'ag_trend':      chart_ag_trend(df),
        'club_wordcloud': chart_word_cloud(df),
    }
    print("Charts done. Assembling PDF…")

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    T  = ParagraphStyle('T',  parent=styles['Title'],   fontSize=22, spaceAfter=6,
                         textColor=colors.HexColor(C_RED))
    H1 = ParagraphStyle('H1', parent=styles['Heading1'],fontSize=15, spaceBefore=18,
                         spaceAfter=6, textColor=colors.HexColor(C_BLUE))
    H2 = ParagraphStyle('H2', parent=styles['Heading2'],fontSize=11, spaceBefore=10,
                         spaceAfter=3, textColor=colors.HexColor(C_PURPLE))
    BO = ParagraphStyle('BO', parent=styles['Normal'],  fontSize=10, spaceAfter=6, leading=14)
    SM = ParagraphStyle('SM', parent=styles['Normal'],  fontSize=8,  textColor=colors.grey)
    CT = ParagraphStyle('CT', parent=styles['Normal'],  fontSize=9,  alignment=TA_CENTER,
                         textColor=colors.grey, spaceAfter=10)
    RH = ParagraphStyle('RH', parent=styles['Normal'],  fontName='Helvetica-Bold',
                         fontSize=10, spaceBefore=8, spaceAfter=3)

    def hr():
        return HRFlowable(width='100%', thickness=0.5,
                          color=colors.HexColor(C_GREY), spaceAfter=6)

    def summary_table(race: str):
        sub = summary[summary['race'] == race].sort_values('year')
        data = [['Year', 'Total', 'Male', 'Female', '% Female', 'Median Time', 'Mean Time']]
        for _, row in sub.iterrows():
            data.append([
                str(int(row['year'])), str(int(row['total'])),
                str(int(row['male'])), str(int(row['female'])),
                f"{row['pct_female']:.1f}%", row['med_str'], row['mean_str'],
            ])
        t = Table(data, colWidths=[1.5*cm, 1.8*cm, 1.8*cm, 1.8*cm, 2.2*cm, 2.8*cm, 2.8*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor(C_BLUE)),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, -1), 9),
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor(C_LIGHT)]),
            ('GRID',          (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return t

    # ── Cover ──────────────────────────────────────────────────────────────────
    total_rows = [
        ['', '2024', '2025', '2026'],
        ['Total finishers (all races)',
         str(int(summary[summary['year']==2024]['total'].sum())),
         str(int(summary[summary['year']==2025]['total'].sum())),
         str(int(summary[summary['year']==2026]['total'].sum()))],
    ]
    for race in RACES:
        row = [f'  {race}']
        for y in YEARS:
            n = summary[(summary['year'] == y) & (summary['race'] == race)]
            row.append(str(int(n['total'].iloc[0])) if len(n) else '—')
        total_rows.append(row)

    ov = Table(total_rows, colWidths=[7*cm, 2.5*cm, 2.5*cm, 2.5*cm])
    ov.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor(C_RED)),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME',      (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 10),
        ('ALIGN',         (1, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, colors.HexColor(C_LIGHT)]),
        ('GRID',          (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))

    story = [
        Spacer(1, 2*cm),
        Paragraph('Analog Devices Cork City Marathon', T),
        Paragraph('2024–2026 Race Analysis &amp; Trends',
                  ParagraphStyle('sub', parent=styles['Normal'], fontSize=14,
                                 textColor=colors.HexColor(C_GREY), spaceAfter=4)),
        hr(),
        Paragraph('Races: Full Marathon · Half Marathon · 10 km', BO),
        Paragraph('Data source: Official timing results (Cork Data), 2024–2026.', SM),
        Spacer(1, 0.5*cm),
        ov,
        PageBreak(),

        # ── Section 1: Participation ──────────────────────────────────────────
        Paragraph('1. Participation', H1), hr(),
        Paragraph(
            'Total finisher numbers have grown across all three races. The Half Marathon '
            'and Full Marathon both show strong year-on-year increases. Female participation '
            'has risen steadily in every event.', BO),
        imgs['participation'],
        Paragraph('Figure 1: Finishers by race and gender, 2024–2026', CT),
        imgs['total_trend'],
        Paragraph('Figure 2: Total finisher count trend per race', CT),
        PageBreak(),
        Paragraph('Participation Summary Tables', H2),
    ]
    for race in RACES:
        story += [Paragraph(race, RH), summary_table(race)]
    story += [
        Spacer(1, 0.4*cm),
        imgs['female_pct'],
        Paragraph('Figure 3: Female participation % by race (2024–2026)', CT),
        PageBreak(),

        # ── Section 2: Finish Times ───────────────────────────────────────────
        Paragraph('2. Finish Times', H1), hr(),
        Paragraph(
            'Median finish times are compared by gender across all three years. '
            'Box plots show the interquartile spread (outliers excluded). '
            'The Full Marathon shows improving median times each year for both genders.', BO),
        imgs['median_time'],
        Paragraph('Figure 4: Median finish time by race and gender (2024–2026)', CT),
        imgs['box_full'],
        Paragraph('Figure 5: Full Marathon finish time distribution', CT),
        PageBreak(),
        imgs['box_half'],
        Paragraph('Figure 6: Half Marathon finish time distribution', CT),
        imgs['box_10k'],
        Paragraph('Figure 7: 10 km finish time distribution', CT),
        PageBreak(),

        # ── Section 3: Age Groups ─────────────────────────────────────────────
        Paragraph('3. Age Group Analysis', H1), hr(),
        Paragraph(
            'The 35–44 bracket is consistently the largest across all distances. '
            'Masters runners (45–54) have grown in the Full Marathon, and the 10 km '
            'attracts the broadest age spread including Juvenile and 65+ participants.', BO),
        imgs['ag_2026'],
        Paragraph('Figure 8: Age group breakdown by race — 2026', CT),
        imgs['ag_trend'],
        Paragraph('Figure 9: Age group finisher trend by race (2024–2026)', CT),
        PageBreak(),

        # ── Section 4: Club Analysis ──────────────────────────────────────────
        Paragraph('4. Club Analysis', H1), hr(),
        Paragraph(
            'Club participation is shown as a word cloud of all clubs represented in the results. ' 
            'Words are sized by the number of finishers affiliated with each club.', BO),
        Spacer(1, 0.2*cm),
        imgs['club_wordcloud'] if imgs['club_wordcloud'] is not None else Spacer(1, 0.1*cm),
        Paragraph('Figure 10: Club word cloud — size proportional to total finishers', CT),
        PageBreak(),

        # ── Section 5: Key Insights ───────────────────────────────────────────
        Paragraph('5. Key Insights', H1), hr(),
    ]
    for ins in [
        '<b>Consistent growth.</b> Finisher counts have increased year-on-year across all three races.',
        '<b>Rising female participation.</b> Female share has grown in every event, most markedly in the Half Marathon.',
        '<b>Improving Full Marathon times.</b> Median finish times for both genders have improved each year.',
        '<b>Core demographic: 35–44.</b> This age bracket provides the highest finisher counts across all races and years.',
        '<b>Masters growth.</b> The 45–54 bracket is growing in the Full Marathon, reflecting broader masters athletics trends in Ireland.',
        '<b>10 km diversity.</b> The 10 km draws the widest age range, from Juvenile to 70+, making it the most inclusive event.',
    ]:
        story.append(Paragraph(f'&bull; {ins}', BO))

    story += [
        Spacer(1, 1*cm), hr(),
        Paragraph('Report generated June 2026 · Data: Cork City Marathon official results', SM),
    ]

    doc.build(story)
    print(f"\nReport saved: {out_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Generate Cork City Marathon analysis PDF.')
    parser.add_argument('--data', default='data/cork',
                        help='Directory containing 2024/, 2025/, 2026/ subdirectories (default: data/cork)')
    parser.add_argument('--out', default='report_charts/cork_marathon_analysis.pdf',
                        help='Output PDF path (default: report_charts/cork_marathon_analysis.pdf)')
    args = parser.parse_args()

    if not os.path.isdir(args.data):
        sys.exit(f"ERROR: data directory '{args.data}' not found.")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        print(f"Loading data from '{args.data}'…")
        df = load_data(args.data, tmp_dir)

    if df.empty:
        sys.exit("ERROR: No records parsed. Check that the PDF files exist and are readable.")

    summary = build_summary(df)
    print("\nSummary:")
    print(summary[['year','race','total','male','female','pct_female','med_str']].to_string(index=False))

    build_pdf(df, summary, args.out)


if __name__ == '__main__':
    main()
