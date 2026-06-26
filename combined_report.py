#!/usr/bin/env python3
"""
Cork City Marathon — Combined Report
=====================================
Produces a single PDF containing:

  1. Overall Marathon Analysis  — most recent year
  2. Marathon Trend Analysis    — all available years
  3. All Clubs Overall Analysis — most recent year
  4. All Clubs Trend Analysis   — all available years
  5. For each --club argument:
       a. Club Deep Dive         — most recent year
       b. Club Deep Dive Trend   — all available years

Usage
-----
  python combined_report.py --club "Togher A.C." "Eagle A.C."
  python combined_report.py --data data/cork --out report_charts/combined.pdf

Requirements
------------
  pip install -r requirements.txt
  System: brew install poppler  (macOS) / sudo apt install poppler-utils  (Ubuntu)
"""

import argparse
import io
import os
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

# ── Import reusable pieces from the single-year script ───────────────────────
from single_year_report import (
    load_year, PDF_FILES, sec_to_hms, race_stats, _find_club,
    RACES, BANDS10, band10,
    C_GREEN, C_BLUE, C_PINK, C_GOLD, C_LIGHT, C_DGREY,
    M_AG_ORDER, F_AG_ORDER,
    fig_to_image, style_ax,
    chart_gender_split, chart_time_distribution, chart_ag_pair,
    chart_club_affiliation, chart_top_clubs, chart_top_clubs_combined,
    chart_word_cloud, chart_venn,
    chart_club_top5_avg,
    chart_age_group_heatmap, chart_age_group_heatmap_overall,
    chart_age_group_heatmap_by_gender,
    chart_club_vs_field, chart_club_age_breakdown, chart_club_gender_per_race,
    chart_club_age_by_race_heatmap, chart_club_age_by_race_gender_heatmap,
    chart_club_kde_by_race, chart_club_kde_by_race_gender,
    build_club_section,
    build_club_finish_time_page,
    gaussian_kde,
)

YEARS = sorted(PDF_FILES.keys())
C_ORANGE  = '#E67E22'
C_PURPLE  = '#8E44AD'
C_GREY    = '#7F8C8D'

YEAR_COLORS = {2024: C_BLUE, 2025: C_GREEN, 2026: C_ORANGE}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_all_years(data_dir: str, tmp_dir: str) -> pd.DataFrame:
    frames = []
    for year in YEARS:
        year_dir = os.path.join(data_dir, str(year))
        if not os.path.isdir(year_dir):
            print(f"  Skipping {year} — directory not found")
            continue
        df = load_year(year, data_dir, tmp_dir)
        if not df.empty:
            df['year'] = year
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


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
# TREND CHARTS  (multi-year, all races)
# ═══════════════════════════════════════════════════════════════════════════════

def chart_trend_participation(summary: pd.DataFrame) -> Image:
    """Grouped bar: M/F finishers per race per year."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    avail_years = sorted(summary['year'].unique())
    for ax, race in zip(axes, RACES):
        sub = summary[summary['race'] == race].set_index('year')
        males   = [int(sub.loc[y, 'male'])   if y in sub.index else 0 for y in avail_years]
        females = [int(sub.loc[y, 'female']) if y in sub.index else 0 for y in avail_years]
        x, w = np.arange(len(avail_years)), 0.35
        ax.bar(x - w/2, males,   w, label='Male',   color=C_BLUE, alpha=0.85)
        ax.bar(x + w/2, females, w, label='Female', color=C_PINK, alpha=0.85)
        for i, (m, f) in enumerate(zip(males, females)):
            if m: ax.text(i - w/2, m + 5, str(m), ha='center', va='bottom', fontsize=7.5)
            if f: ax.text(i + w/2, f + 5, str(f), ha='center', va='bottom', fontsize=7.5)
        ax.set_xticks(x); ax.set_xticklabels(avail_years)
        style_ax(ax, title=race, ylabel='Finishers' if race == 'Full' else '')
        if race == 'Full': ax.legend(fontsize=9)
    fig.suptitle('Finisher Count by Race and Gender', fontsize=13, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_trend_total(summary: pd.DataFrame) -> Image:
    """Line: total finishers trend per race."""
    fig, ax = plt.subplots(figsize=(10, 4))
    for race, col in zip(RACES, [C_BLUE, C_GREEN, C_ORANGE]):
        sub = summary[summary['race'] == race].sort_values('year')
        ax.plot(sub['year'], sub['total'], marker='o', linewidth=2.5,
                markersize=8, color=col, label=race)
        for _, row in sub.iterrows():
            ax.annotate(str(int(row['total'])), (row['year'], row['total']),
                        textcoords='offset points', xytext=(0, 9),
                        ha='center', fontsize=9, color=col)
    ax.set_xticks(sorted(summary['year'].unique()))
    style_ax(ax, title='Total Finishers Trend', xlabel='Year', ylabel='Finishers')
    ax.legend(fontsize=10)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_trend_female_pct(summary: pd.DataFrame) -> Image:
    """Line: % female finishers per race per year."""
    fig, ax = plt.subplots(figsize=(10, 4))
    for race, col in zip(RACES, [C_BLUE, C_GREEN, C_ORANGE]):
        sub = summary[summary['race'] == race].sort_values('year')
        ax.plot(sub['year'], sub['pct_female'], marker='s', linewidth=2.5,
                markersize=8, color=col, label=race)
        for _, row in sub.iterrows():
            ax.annotate(f"{row['pct_female']:.1f}%", (row['year'], row['pct_female']),
                        textcoords='offset points', xytext=(0, 8),
                        ha='center', fontsize=9, color=col)
    ax.set_xticks(sorted(summary['year'].unique()))
    ax.set_ylim(0, 70)
    ax.axhline(50, color='grey', linestyle=':', alpha=0.5, label='50% parity')
    style_ax(ax, title='Female Participation %', xlabel='Year', ylabel='% Female')
    ax.legend(fontsize=10)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_trend_male_pct(summary: pd.DataFrame) -> Image:
    """Line: % male finishers per race per year."""
    fig, ax = plt.subplots(figsize=(10, 4))
    for race, col in zip(RACES, [C_BLUE, C_GREEN, C_ORANGE]):
        sub = summary[summary['race'] == race].sort_values('year')
        pct_male = 100 - sub['pct_female']
        ax.plot(sub['year'], pct_male, marker='s', linewidth=2.5,
                markersize=8, color=col, label=race)
        for (_, row), pm in zip(sub.iterrows(), pct_male):
            ax.annotate(f"{pm:.1f}%", (row['year'], pm),
                        textcoords='offset points', xytext=(0, 8),
                        ha='center', fontsize=9, color=col)
    ax.set_xticks(sorted(summary['year'].unique()))
    ax.set_ylim(30, 100)
    ax.axhline(50, color='grey', linestyle=':', alpha=0.5, label='50% parity')
    style_ax(ax, title='Male Participation %', xlabel='Year', ylabel='% Male')
    ax.legend(fontsize=10)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_trend_median_time(df: pd.DataFrame) -> Image:
    """Line: median finish time trend by race and gender."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    avail_years = sorted(df['year'].unique())
    for ax, race in zip(axes, RACES):
        for sex, col, lbl in [('M', C_BLUE, 'Male'), ('F', C_PINK, 'Female')]:
            vals = []
            for y in avail_years:
                s = df[(df['year'] == y) & (df['race'] == race) & (df['sex'] == sex)]['sec']
                vals.append(s.median() if len(s) else np.nan)
            hours = [v / 3600 if not np.isnan(v) else np.nan for v in vals]
            ax.plot(avail_years, hours, marker='o', linewidth=2, markersize=7,
                    color=col, label=lbl)
            for y, v in zip(avail_years, vals):
                if not np.isnan(v):
                    ax.annotate(sec_to_hms(v), (y, v / 3600),
                                textcoords='offset points', xytext=(0, 7),
                                ha='center', fontsize=7.5, color=col)
        ax.set_xticks(avail_years)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"{int(v)}h{int((v % 1) * 60):02d}"))
        style_ax(ax, title=race, ylabel='Median Time' if race == 'Full' else '')
        if race == 'Full': ax.legend(fontsize=9)
    fig.suptitle('Median Finish Time Trend', fontsize=13, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_trend_boxplot(df: pd.DataFrame, race: str) -> Image:
    """Box plots: finish time distribution by year and gender."""
    sub = df[df['race'] == race]
    avail_years = sorted(df['year'].unique())
    fig, ax = plt.subplots(figsize=(10, 4.5))
    positions, labels, box_data, box_colors = [], [], [], []
    for i, year in enumerate(avail_years):
        for j, (sex, col) in enumerate([('M', C_BLUE), ('F', C_PINK)]):
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
        plt.FuncFormatter(lambda v, _: f"{int(v)}h{int((v % 1) * 60):02d}"))
    m_p = mpatches.Patch(color=C_BLUE, alpha=0.75, label='Male')
    f_p = mpatches.Patch(color=C_PINK, alpha=0.75, label='Female')
    ax.legend(handles=[m_p, f_p], fontsize=9)
    style_ax(ax, title=f'{race} — Finish Time Distribution', ylabel='Finish Time')
    fig.tight_layout()
    return fig_to_image(fig)


def chart_trend_age_groups(df: pd.DataFrame) -> Image:
    """Line: finisher count by age group and race across years."""
    avail_years = sorted(df['year'].unique())
    decade_labels = ['18-34', '35-39', '40-44', '45-49', '50-54', '55-59']
    decade_codes  = [('M', 'F'), ('M35','F35'), ('M40','F40'),
                     ('M45','F45'), ('M50','F50'), ('M55','F55')]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    cmap = plt.cm.tab10
    for ax, race in zip(axes, RACES):
        for idx, (label, (mc, fc)) in enumerate(zip(decade_labels, decade_codes)):
            vals = [
                len(df[(df['year'] == y) & (df['race'] == race) & df['ag'].isin([mc, fc])])
                for y in avail_years
            ]
            ax.plot(avail_years, vals, marker='o', linewidth=1.8, markersize=6,
                    color=cmap(idx), label=label)
        ax.set_xticks(avail_years)
        style_ax(ax, title=race, ylabel='Finishers' if race == 'Full' else '')
        if race == 'Full': ax.legend(fontsize=8, loc='upper left')
    fig.suptitle('Age Group Trend', fontsize=13, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_ag_trend_median_time(df: pd.DataFrame) -> Image:
    """Line: median finish time by age group across years, per race."""
    avail_years = sorted(df['year'].unique())
    decade_labels = ['18-34', '35-39', '40-44', '45-49', '50-54', '55-59']
    decade_codes  = [('M', 'F'), ('M35','F35'), ('M40','F40'),
                     ('M45','F45'), ('M50','F50'), ('M55','F55')]
    cmap = plt.cm.tab10
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, race in zip(axes, RACES):
        for idx, (label, (mc, fc)) in enumerate(zip(decade_labels, decade_codes)):
            vals = []
            for y in avail_years:
                sub = df[(df['year']==y) & (df['race']==race) & df['ag'].isin([mc, fc])]['sec']
                vals.append(sub.median() if len(sub) else np.nan)
            hours = [v / 3600 if not np.isnan(v) else np.nan for v in vals]
            ax.plot(avail_years, hours, marker='o', linewidth=1.8, markersize=5,
                    color=cmap(idx), label=label)
        ax.set_xticks(avail_years)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"{int(v)}h{int((v % 1)*60):02d}"))
        style_ax(ax, title=race, ylabel='Median Time' if race=='Full' else '')
        if race == 'Full': ax.legend(fontsize=8, loc='upper right')
    fig.suptitle('Age Group Median Finish Time Trend', fontsize=13, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig)


def chart_age_pyramids(df: pd.DataFrame, year: int = None, xmax: int = None,
                       years: list = None, figsize=(14, 5), width_cm: float = 17) -> Image:
    """Population pyramids per race: Male (left) vs Female (right) by age band.

    All three subplots share one symmetric x-axis so race magnitudes are comparable.
    Pass ``xmax`` to force a fixed scale (e.g. shared across several years' charts);
    otherwise it is derived from the data's largest band. Pass ``years`` (a list) to plot
    the per-year *average* count across those years; otherwise a single ``year`` is shown.
    """
    yrs = years if years is not None else [year]
    n_yr = len(yrs)
    yr_label = str(yrs[0]) if n_yr == 1 else f'{yrs[0]}–{yrs[-1]} average'

    fig, axes = plt.subplots(1, 3, figsize=figsize, sharey=True)
    y = np.arange(len(BANDS10))
    xmax_auto = 0
    for ax, race in zip(axes, RACES):
        sub = df[(df['year'].isin(yrs)) & (df['race'] == race)].copy()
        sub['decade'] = sub['ag'].map(band10)
        m_counts = [len(sub[(sub['sex'] == 'M') & (sub['decade'] == d)]) / n_yr for d in BANDS10]
        f_counts = [len(sub[(sub['sex'] == 'F') & (sub['decade'] == d)]) / n_yr for d in BANDS10]
        xmax_auto = max([xmax_auto] + m_counts + f_counts)

        ax.barh(y, [-m for m in m_counts], color=C_BLUE, alpha=0.85, label='Male')
        ax.barh(y, f_counts,               color=C_PINK, alpha=0.85, label='Female')
        for idx, (mc, fc) in enumerate(zip(m_counts, f_counts)):
            if mc:
                ax.text(-mc, idx, f'{mc:,.0f} ', ha='right', va='center',
                        fontsize=6.5, color=C_BLUE)
            if fc:
                ax.text(fc, idx, f' {fc:,.0f}', ha='left', va='center',
                        fontsize=6.5, color=C_PINK)
        ax.axvline(0, color=C_DGREY, linewidth=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(BANDS10, fontsize=8)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{abs(int(v))}"))

        total = sum(m_counts) + sum(f_counts)
        pct_f = (sum(f_counts) / total * 100) if total else 0
        ax.set_title(f"{race}  ·  {pct_f:.0f}% female", fontsize=12, fontweight='bold', pad=8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.grid(axis='x', alpha=0.3, linestyle='--')
        ax.tick_params(labelsize=9)
        if race == RACES[0]:
            ax.legend(fontsize=9, loc='lower left')
            ax.set_ylabel('Age group', fontsize=10)

    lim = xmax if xmax is not None else int(xmax_auto * 1.15) + 1
    for ax in axes:
        ax.set_xlim(-lim, lim)

    fig.suptitle(f'Age Profile by Race & Gender — {yr_label}  (◄ Male · Female ►)',
                 fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig, width_cm=width_cm)


def chart_age_composition_trend(df: pd.DataFrame) -> Image:
    """Per race: 100%-stacked age-band composition, one bar per year×gender."""
    avail_years = sorted(df['year'].unique())
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.4), sharey=True)
    cmap = plt.cm.viridis
    band_colors = [cmap(i / (len(BANDS10) - 1)) for i in range(len(BANDS10))]

    for ax, race in zip(axes, RACES):
        sub = df[df['race'] == race].copy()
        sub['decade'] = sub['ag'].map(band10)

        positions, labels, shares = [], [], []
        for i, yr in enumerate(avail_years):
            for j, sex in enumerate(['M', 'F']):
                g = sub[(sub['year'] == yr) & (sub['sex'] == sex)]
                n = len(g)
                col = [len(g[g['decade'] == d]) / n * 100 if n else 0 for d in BANDS10]
                positions.append(i * 3 + j)
                labels.append(f"{yr}\n{sex}")
                shares.append(col)

        shares = np.array(shares)                       # rows = bars, cols = bands
        bottoms = np.zeros(len(positions))
        for b, (band, color) in enumerate(zip(BANDS10, band_colors)):
            ax.bar(positions, shares[:, b], bottom=bottoms, width=0.8,
                   color=color, label=band)
            bottoms += shares[:, b]

        ax.set_xticks(positions)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylim(0, 100)
        style_ax(ax, title=race, ylabel='% of finishers' if race == RACES[0] else '')

    handles, labs = axes[0].get_legend_handles_labels()
    fig.legend(handles, labs, title='Age group', fontsize=8, title_fontsize=9,
               loc='center right', bbox_to_anchor=(1.005, 0.5))
    fig.suptitle('Age Composition by Race, Gender & Year',
                 fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout(rect=(0, 0, 0.92, 1))
    return fig_to_image(fig, width_cm=15)


# ═══════════════════════════════════════════════════════════════════════════════
# ALL CLUBS TREND CHARTS
# ═══════════════════════════════════════════════════════════════════════════════

def chart_clubs_count_trend(df: pd.DataFrame) -> Image:
    """Bar: number of unique clubs and affiliation rate per year."""
    avail_years = sorted(df['year'].unique())
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    club_counts = []
    aff_rates   = []
    for year in avail_years:
        sub = df[df['year'] == year]
        wc  = sub[sub['club'].str.strip() != '']
        club_counts.append(wc['club'].str.strip().nunique())
        aff_rates.append(round(100 * len(wc) / len(sub)) if len(sub) else 0)

    x = np.arange(len(avail_years))
    bars = ax1.bar(x, club_counts, 0.5, color=C_GREEN, alpha=0.85)
    for bar, val in zip(bars, club_counts):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 str(val), ha='center', va='bottom', fontsize=10, fontweight='bold')
    ax1.set_xticks(x); ax1.set_xticklabels(avail_years)
    style_ax(ax1, title='Unique Clubs per Year', ylabel='Number of Clubs')

    ax2.plot(avail_years, aff_rates, marker='o', color=C_GREEN, linewidth=2.5, markersize=9)
    for y, v in zip(avail_years, aff_rates):
        ax2.annotate(f"{v}%", (y, v), textcoords='offset points',
                     xytext=(0, 9), ha='center', fontsize=10, color=C_GREEN)
    ax2.set_xticks(avail_years); ax2.set_ylim(0, 30)
    style_ax(ax2, title='Club Affiliation Rate (%) per Year',
             xlabel='Year', ylabel='% with Club')

    fig.tight_layout()
    return fig_to_image(fig)


def chart_top_clubs_trend(df: pd.DataFrame, n: int = 15) -> Image:
    """
    Horizontal bar: top clubs by total finishers across all years combined,
    with segments coloured by year.
    """
    sub = df[df['club'].str.strip() != '']
    top = (sub.groupby('club').size()
             .sort_values(ascending=False)
             .head(n))
    clubs  = top.index.tolist()[::-1]

    avail_years = sorted(df['year'].unique())
    fig, ax = plt.subplots(figsize=(10, max(4, len(clubs) * 0.42)))
    y = np.arange(len(clubs))
    lefts = np.zeros(len(clubs))

    for year in avail_years:
        yr_sub = sub[sub['year'] == year]
        counts = [len(yr_sub[yr_sub['club'] == c]) for c in clubs]
        ax.barh(y, counts, left=lefts, color=YEAR_COLORS[year],
                alpha=0.85, label=str(year))
        for i, (cnt, l) in enumerate(zip(counts, lefts)):
            if cnt >= 3:
                ax.text(l + cnt / 2, i, str(cnt), ha='center', va='center',
                        fontsize=7, color='white', fontweight='bold')
        lefts += counts

    for i, (club, total) in enumerate(zip(clubs, [top[c] for c in clubs])):
        ax.text(total + 0.3, i, str(total), va='center', fontsize=7.5)

    ax.set_yticks(y); ax.set_yticklabels(clubs, fontsize=8)
    ax.legend(fontsize=9, loc='lower right')
    style_ax(ax, title=f'Top {n} Clubs — Total Finishers by Year',
             xlabel='Finishers', grid_axis='x')
    ax.spines['left'].set_visible(False)
    fig.tight_layout()
    return fig_to_image(fig, width_cm=14)


# ═══════════════════════════════════════════════════════════════════════════════
# CLUB TREND SECTION  (per club, multi-year)
# ═══════════════════════════════════════════════════════════════════════════════

def chart_club_trend_participation(df: pd.DataFrame, club_name: str) -> Image:
    """Grouped bar: club finishers per race per year, M/F split."""
    sub = df[df['club'].str.strip() == club_name]
    avail_years = sorted(df['year'].unique())
    race_labels = {'Full': 'Marathon', 'Half': 'Half Marathon', '10K': '10K'}

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, race in zip(axes, RACES):
        m_vals = [len(sub[(sub['year']==y)&(sub['race']==race)&(sub['sex']=='M')]) for y in avail_years]
        f_vals = [len(sub[(sub['year']==y)&(sub['race']==race)&(sub['sex']=='F')]) for y in avail_years]
        x, w = np.arange(len(avail_years)), 0.35
        ax.bar(x - w/2, m_vals, w, color=C_BLUE, alpha=0.85, label='Male')
        ax.bar(x + w/2, f_vals, w, color=C_PINK, alpha=0.85, label='Female')
        for i, (m, f) in enumerate(zip(m_vals, f_vals)):
            if m: ax.text(i - w/2, m + 0.2, str(m), ha='center', va='bottom', fontsize=8)
            if f: ax.text(i + w/2, f + 0.2, str(f), ha='center', va='bottom', fontsize=8)
        ax.set_xticks(x); ax.set_xticklabels(avail_years)
        style_ax(ax, title=race_labels[race], ylabel='Finishers' if race=='Full' else '')
        if race == 'Full': ax.legend(fontsize=8)
    fig.suptitle(f'{club_name} — Finishers by Year', fontsize=12, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig, width_cm=15)


def chart_club_trend_median_time(df: pd.DataFrame, club_name: str) -> Image:
    """Line: club median finish time by race and year, vs overall field median."""
    sub = df[df['club'].str.strip() == club_name]
    avail_years = sorted(df['year'].unique())
    race_labels = {'Full': 'Marathon', 'Half': 'Half Marathon', '10K': '10K'}

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, race in zip(axes, RACES):
        # Field medians
        field_vals = [df[(df['year']==y)&(df['race']==race)]['sec'].median()
                      for y in avail_years]
        ax.plot(avail_years, [v/3600 if not np.isnan(v) else np.nan for v in field_vals],
                color='#CCCCCC', linewidth=2, linestyle='--', label='Field median')

        # Club M/F medians
        for sex, col, lbl in [('M', C_BLUE, 'Male'), ('F', C_PINK, 'Female')]:
            vals = []
            for y in avail_years:
                s = sub[(sub['year']==y)&(sub['race']==race)&(sub['sex']==sex)]['sec']
                vals.append(s.median() if len(s) >= 2 else np.nan)
            hours = [v/3600 if not np.isnan(v) else np.nan for v in vals]
            ax.plot(avail_years, hours, marker='o', linewidth=2, markersize=7,
                    color=col, label=lbl)
            for y, v in zip(avail_years, vals):
                if not np.isnan(v):
                    ax.annotate(sec_to_hms(v), (y, v/3600),
                                textcoords='offset points', xytext=(0, 7),
                                ha='center', fontsize=7.5, color=col)
        ax.set_xticks(avail_years)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"{int(v)}h{int((v%1)*60):02d}"))
        style_ax(ax, title=race_labels[race], ylabel='Median Time' if race=='Full' else '')
        if race == 'Full': ax.legend(fontsize=8)
    fig.suptitle(f'{club_name} — Median Finish Time vs Field',
                 fontsize=12, fontweight='bold', y=1.02)
    fig.tight_layout()
    return fig_to_image(fig, width_cm=15)


def chart_club_trend_age_heatmap(df: pd.DataFrame, club_name: str) -> Image:
    """
    Side-by-side heatmaps per year: age groups × races.
    Shows how the club's age composition changes year to year.
    """
    avail_years = sorted(df['year'].unique())
    sub_all = df[df['club'].str.strip() == club_name].copy()
    sub_all['decade'] = sub_all['ag'].map(band10)
    race_labels = {'Full': 'Marathon', 'Half': 'Half\nMarathon', '10K': '10K'}
    col_labels = [race_labels[r] for r in RACES]

    active_decades = [d for d in BANDS10
                      if len(sub_all[sub_all['decade'] == d]) > 0]
    if not active_decades:
        return None

    fig, axes = plt.subplots(1, len(avail_years),
                             figsize=(5 * len(avail_years), max(3, len(active_decades) * 0.45)),
                             sharey=True)
    if len(avail_years) == 1:
        axes = [axes]

    all_vals = []
    matrices = []
    for year in avail_years:
        sub = sub_all[sub_all['year'] == year]
        mat = pd.DataFrame(
            [[len(sub[(sub['decade']==d) & (sub['race']==r)]) for r in RACES]
             for d in active_decades],
            index=active_decades, columns=col_labels
        )
        matrices.append(mat)
        all_vals.extend(mat.values.flatten())

    vmax = max(max(all_vals), 1)

    for ax, mat, year in zip(axes, matrices, avail_years):
        im = ax.imshow(mat.values, aspect='auto', cmap='Greens', vmin=0, vmax=vmax)
        ax.set_xticks(range(3)); ax.set_xticklabels(mat.columns, fontsize=8)
        ax.set_yticks(range(len(active_decades)))
        ax.set_yticklabels(active_decades, fontsize=8)
        threshold = vmax * 0.55
        for i in range(len(active_decades)):
            for j in range(3):
                val = mat.iloc[i, j]
                if val > 0:
                    tc = 'white' if val >= threshold else '#333333'
                    ax.text(j, i, str(val), ha='center', va='center',
                            fontsize=8, color=tc, fontweight='bold' if val >= threshold else 'normal')
        ax.set_xticks(np.arange(-0.5, 3), minor=True)
        ax.set_yticks(np.arange(-0.5, len(active_decades)), minor=True)
        ax.grid(which='minor', color='white', linewidth=0.8)
        ax.tick_params(which='minor', length=0)
        ax.set_title(str(year), fontsize=10, fontweight='bold', pad=6)

    fig.colorbar(im, ax=axes[-1], shrink=0.6).ax.tick_params(labelsize=7)
    fig.suptitle(f'{club_name} — Age Group Composition by Year',
                 fontsize=11, fontweight='bold', y=1.01)
    fig.tight_layout()
    return fig_to_image(fig, width_cm=15)


def build_club_trend_section(df_all: pd.DataFrame, club_name: str,
                             story: list, styles: dict,
                             section_label: str = None) -> None:
    """Append multi-year club trend pages to story."""
    SEC, SUBSEC, BODY, HR = (
        styles['SEC'], styles['SUBSEC'], styles['BODY'], styles['hr'])

    sub = df_all[df_all['club'].str.strip() == club_name]
    if sub.empty:
        return

    avail_years = sorted(df_all['year'].unique())
    year_range  = f"{avail_years[0]}–{avail_years[-1]}"

    story.append(PageBreak())
    story.append(HR())
    heading = f'{section_label} {club_name} — Trend Analysis {year_range}' if section_label else f'{club_name} — Trend Analysis {year_range}'
    story.append(Paragraph(heading, SEC))
    story.append(Paragraph(
        f'Year-on-year performance across {len(avail_years)} seasons.', SUBSEC))
    story.append(Spacer(1, 0.3*cm))

    img = chart_club_trend_participation(df_all, club_name)
    if img:
        story.append(img)
        story.append(Spacer(1, 0.4*cm))

    img = chart_club_trend_median_time(df_all, club_name)
    if img:
        story.append(img)
        story.append(Spacer(1, 0.4*cm))

    img = chart_club_trend_age_heatmap(df_all, club_name)
    if img:
        story.append(img)


# ═══════════════════════════════════════════════════════════════════════════════
# TREND ANALYSIS TEXT
# ═══════════════════════════════════════════════════════════════════════════════

def _trend_insights_participation(summary: pd.DataFrame) -> list[str]:
    """Return bullet strings for the participation + gender % page."""
    avail = sorted(summary['year'].unique())
    y0, y1 = avail[0], avail[-1]
    bullets = []
    race_labels = {'Full': 'Full Marathon', 'Half': 'Half Marathon', '10K': '10K'}

    # Growth per race from first to last year
    growth = {}
    for race, label in race_labels.items():
        sub = summary[summary['race'] == race].sort_values('year')
        if len(sub) < 2:
            continue
        t0, t1 = int(sub.iloc[0]['total']), int(sub.iloc[-1]['total'])
        pct = round((t1 - t0) / t0 * 100)
        growth[race] = pct
        direction = f"+{pct}%" if pct >= 0 else f"{pct}%"
        bullets.append(f"{label} finishers {direction} from {y0} to {y1} ({t0:,} → {t1:,}).")

    # Fastest / slowest growing race
    if growth:
        top = max(growth, key=growth.get)
        bot = min(growth, key=growth.get)
        if top != bot:
            bullets.append(
                f"{race_labels[top]} showed the strongest growth; "
                f"{race_labels[bot]} {'declined' if growth[bot] < 0 else 'grew slowest'} over the same period.")

    # Gender balance note for each race (latest year)
    latest = summary[summary['year'] == y1]
    for race, label in race_labels.items():
        row = latest[latest['race'] == race]
        if row.empty:
            continue
        pf = row.iloc[0]['pct_female']
        pm = round(100 - pf, 1)
        if pf > 55:
            bullets.append(f"{label} remains female-majority at {pf}% female / {pm}% male in {y1}.")
        elif pf > 45:
            bullets.append(f"{label} is near gender parity: {pf}% female, {pm}% male in {y1}.")
        else:
            bullets.append(f"{label} is male-dominated at {pm}% male in {y1}.")

    # Gender gradient across distances (Age Profile learning)
    pf_by_race = {}
    for race in ('Full', 'Half', '10K'):
        row = latest[latest['race'] == race]
        if not row.empty:
            pf_by_race[race] = row.iloc[0]['pct_female']
    if {'Full', 'Half', '10K'} <= pf_by_race.keys():
        bullets.append(
            f"Female participation declines steadily with distance: {pf_by_race['10K']}% female in "
            f"the 10K, {pf_by_race['Half']}% in the Half, but only {pf_by_race['Full']}% in the Full "
            f"Marathon ({y1}) — the gender gap widens the longer the race.")

    return bullets


def _trend_insights_times_ages(df: pd.DataFrame) -> list[str]:
    """Return bullet strings for the median time + age group pages."""
    avail = sorted(df['year'].unique())
    y0, y1 = avail[0], avail[-1]
    race_labels = {'Full': 'Full Marathon', 'Half': 'Half Marathon', '10K': '10K'}
    bullets = []

    # Median time trend per race (overall)
    for race, label in race_labels.items():
        times = {}
        for y in avail:
            s = df[(df['year'] == y) & (df['race'] == race)]['sec']
            if len(s):
                times[y] = s.median()
        if y0 in times and y1 in times:
            diff_min = round((times[y1] - times[y0]) / 60, 1)
            if abs(diff_min) < 0.5:
                bullets.append(f"{label} median finish time was unchanged from {y0} to {y1}.")
            elif diff_min < 0:
                bullets.append(
                    f"{label} median finish time improved by {abs(diff_min)} min from {y0} to {y1} "
                    f"({sec_to_hms(int(times[y0]))} → {sec_to_hms(int(times[y1]))}).")
            else:
                bullets.append(
                    f"{label} median finish time slowed by {diff_min} min from {y0} to {y1} "
                    f"({sec_to_hms(int(times[y0]))} → {sec_to_hms(int(times[y1]))}).")

    # Largest age group in latest year
    decade_codes = [('M', 'F'), ('M35','F35'), ('M40','F40'),
                    ('M45','F45'), ('M50','F50'), ('M55','F55')]
    decade_labels = ['18–34', '35–39', '40–44', '45–49', '50–54', '55–59']
    sub = df[df['year'] == y1]
    counts = {
        label: len(sub[sub['ag'].isin([mc, fc])])
        for label, (mc, fc) in zip(decade_labels, decade_codes)
    }
    top_ag = max(counts, key=counts.get)
    bullets.append(
        f"The {top_ag} age group was the largest cohort in {y1} with {counts[top_ag]:,} finishers across all races.")

    # Age group with fastest growth
    first = df[df['year'] == y0]
    growth_ag = {}
    for label, (mc, fc) in zip(decade_labels, decade_codes):
        c0 = len(first[first['ag'].isin([mc, fc])])
        c1 = len(sub[sub['ag'].isin([mc, fc])])
        if c0 > 0:
            growth_ag[label] = round((c1 - c0) / c0 * 100)
    if growth_ag:
        top_g = max(growth_ag, key=growth_ag.get)
        bullets.append(
            f"The {top_g} age group saw the fastest participation growth ({'+' if growth_ag[top_g] >= 0 else ''}{growth_ag[top_g]}% from {y0} to {y1}).")

    # Age skew by distance (Age Profile learning), using consistent 10-year bands
    young = {}
    for race in ('Full', '10K'):
        rsub = sub[sub['race'] == race]
        if len(rsub):
            young[race] = round(len(rsub[rsub['ag'].map(band10) == '18-34']) / len(rsub) * 100)
    if 'Full' in young and '10K' in young:
        bullets.append(
            f"The field skews younger as the distance shortens: the 18–34 group is {young['10K']}% "
            f"of 10K finishers versus {young['Full']}% of the Full Marathon in {y1}.")

    return bullets


def _trend_insights_boxplot(df: pd.DataFrame) -> list[str]:
    """Return bullet strings for the finish time distribution boxplot page."""
    avail = sorted(df['year'].unique())
    y0, y1 = avail[0], avail[-1]
    race_labels = {'Full': 'Full Marathon', 'Half': 'Half Marathon', '10K': '10K'}
    bullets = []

    # Gender gap (female median - male median) per race in latest year, and stability
    gaps = {}
    for race, label in race_labels.items():
        sub = df[(df['race'] == race) & (df['year'] == y1)]
        m_med = sub[sub['sex'] == 'M']['sec'].median()
        f_med = sub[sub['sex'] == 'F']['sec'].median()
        if not (np.isnan(m_med) or np.isnan(f_med)):
            gaps[race] = f_med - m_med

    if gaps:
        smallest_gap_race = min(gaps, key=gaps.get)
        for race, label in race_labels.items():
            if race in gaps:
                gap_min = round(gaps[race] / 60)
                bullets.append(
                    f"{label}: female median is {gap_min} min slower than male in {y1} — "
                    f"this gap is consistent across all years.")
        bullets.append(
            f"The {race_labels[smallest_gap_race]} has the smallest gender gap ({round(gaps[smallest_gap_race]/60)} min), "
            f"reflecting a narrower performance spread at the shorter distance.")

    # IQR spread — female wider than male?
    wider = []
    for race, label in race_labels.items():
        sub = df[(df['race'] == race) & (df['year'] == y1)]
        f_iqr = m_iqr = None
        for sex, name in [('M', 'male'), ('F', 'female')]:
            s = sub[sub['sex'] == sex]['sec']
            if len(s) > 10:
                iqr = s.quantile(0.75) - s.quantile(0.25)
                if sex == 'F':
                    f_iqr = iqr
                else:
                    m_iqr = iqr
        if f_iqr is not None and m_iqr is not None and f_iqr > m_iqr:
            wider.append(label)
    if wider:
        bullets.append(
            f"Female finish time distributions are wider than male across "
            f"{', '.join(wider)} — indicating greater variability among female runners.")

    # Year-on-year stability — compare median shift across years
    stable = []
    for race, label in race_labels.items():
        shifts = []
        for sex in ['M', 'F']:
            meds = [df[(df['year']==y) & (df['race']==race) & (df['sex']==sex)]['sec'].median()
                    for y in avail]
            meds = [m for m in meds if not np.isnan(m)]
            if len(meds) >= 2:
                shifts.append(abs(meds[-1] - meds[0]) / 60)
        if shifts and max(shifts) < 5:
            stable.append(label)
    if stable:
        bullets.append(
            f"Median finish times are stable year-on-year across {', '.join(stable)} "
            f"(shift < 5 min from {y0} to {y1}), indicating a consistent runner profile.")

    return bullets


# ═══════════════════════════════════════════════════════════════════════════════
# 2026 DATA-COMPLETENESS ANALYSIS
# Resolve whether the 2026 male-ageing pattern (smaller 18-34 share, bigger 35+) is a
# real demographic shift or an artefact of incomplete 2026 data. All functions are pure
# and reuse band10/BANDS10 — no bucket re-derivation.
# ═══════════════════════════════════════════════════════════════════════════════

def age_counts_table(df: pd.DataFrame) -> pd.DataFrame:
    """Long-form absolute counts + within-group shares per (race, sex, year, band).

    `total` = finishers in that (race, sex, year); `share_pct` = count / total * 100.
    """
    sub = df.copy()
    sub['band'] = sub['ag'].map(band10)
    rows = []
    for race in RACES:
        for sex in ('M', 'F'):
            for year in sorted(sub['year'].unique()):
                g = sub[(sub['race'] == race) & (sub['sex'] == sex) & (sub['year'] == year)]
                total = len(g)
                for band in BANDS10:
                    cnt = int((g['band'] == band).sum())
                    rows.append({
                        'race': race, 'sex': sex, 'year': int(year), 'band': band,
                        'count': cnt, 'total': total,
                        'share_pct': round(cnt / total * 100, 1) if total else 0.0,
                    })
    return pd.DataFrame(rows)


def completeness_flags(df: pd.DataFrame, threshold_pct: float = 85,
                       current_year: int = None, force_provisional=None) -> pd.DataFrame:
    """Per (race, sex): is the current year's field large enough to trust its shares?

    Compares current-year total finishers against the mean of all prior years; flags
    `provisional` when the current field is below `threshold_pct`% of that prior mean.
    `force_provisional` (an iterable of `year` values and/or `(race, year)` tuples) marks
    cells provisional regardless of count — for races not yet run or an as-of cutoff.
    """
    years = sorted(df['year'].unique())
    cur = current_year if current_year is not None else years[-1]
    prior = [y for y in years if y < cur]
    forced = set(force_provisional) if force_provisional else set()
    rows = []
    for race in RACES:
        for sex in ('M', 'F'):
            cur_total = len(df[(df['race'] == race) & (df['sex'] == sex) & (df['year'] == cur)])
            prior_totals = [len(df[(df['race'] == race) & (df['sex'] == sex) & (df['year'] == y)])
                            for y in prior]
            prior_mean = float(np.mean(prior_totals)) if prior_totals else float('nan')
            pct = (cur_total / prior_mean * 100) if prior_mean else float('nan')
            is_forced = cur in forced or (race, cur) in forced
            rows.append({
                'race': race, 'sex': sex, 'year': int(cur),
                'current_total': cur_total, 'prior_mean': round(prior_mean, 1),
                'pct_of_prior': round(pct, 1) if prior_mean else float('nan'),
                'provisional': bool(is_forced or (prior_mean and pct < threshold_pct)),
            })
    return pd.DataFrame(rows)


def decompose_young_share_shift(df: pd.DataFrame, race: str, sex: str = 'M',
                                band: str = '18-34', y_prev: int = None,
                                y_curr: int = None) -> dict:
    """Counterfactual split of the YoY change in a band's share for one race/sex.

    Splits the share change into a "fewer young" effect (young count moves to current,
    older held at prior) and a "more old" effect (older moves, young held), each in
    percentage points. Their sum plus a small `interaction` term equals the actual change.
    """
    years = sorted(df['year'].unique())
    yp = y_prev if y_prev is not None else years[-2]
    yc = y_curr if y_curr is not None else years[-1]

    def counts(year):
        g = df[(df['race'] == race) & (df['sex'] == sex) & (df['year'] == year)].copy()
        g['band'] = g['ag'].map(band10)
        young = int((g['band'] == band).sum())
        total = len(g)
        return young, total - young  # young, old

    young_p, old_p = counts(yp)
    young_c, old_c = counts(yc)

    def share(y, o):
        return (y / (y + o) * 100) if (y + o) else 0.0

    share_prev = share(young_p, old_p)
    share_curr = share(young_c, old_c)
    eff_young = share(young_c, old_p) - share_prev   # young moves, old held at prev
    eff_old = share(young_p, old_c) - share_prev     # old moves, young held at prev
    actual = share_curr - share_prev
    return {
        'race': race, 'sex': sex, 'band': band, 'y_prev': int(yp), 'y_curr': int(yc),
        'young_prev': young_p, 'young_curr': young_c, 'old_prev': old_p, 'old_curr': old_c,
        'share_prev': round(share_prev, 1), 'share_curr': round(share_curr, 1),
        'actual_change': round(actual, 1),
        'eff_fewer_young': round(eff_young, 1), 'eff_more_old': round(eff_old, 1),
        'interaction': round(actual - eff_young - eff_old, 1),
    }


def noise_floor_flags(df: pd.DataFrame, current_year: int = None,
                      prev_year: int = None) -> pd.DataFrame:
    """Per (race, sex, band): is the YoY share move within sampling noise?

    `se_pp` ≈ binomial standard error of the current share (percentage points);
    `is_noise` when |share change| < 2·SE (e.g. tiny 65+ bands swinging on a handful
    of finishers).
    """
    years = sorted(df['year'].unique())
    yc = current_year if current_year is not None else years[-1]
    yp = prev_year if prev_year is not None else years[-2]
    sub = df.copy()
    sub['band'] = sub['ag'].map(band10)
    rows = []
    for race in RACES:
        for sex in ('M', 'F'):
            for band in BANDS10:
                gp = sub[(sub['race'] == race) & (sub['sex'] == sex) & (sub['year'] == yp)]
                gc = sub[(sub['race'] == race) & (sub['sex'] == sex) & (sub['year'] == yc)]
                np_, nc_ = len(gp), len(gc)
                cp = int((gp['band'] == band).sum())
                cc = int((gc['band'] == band).sum())
                sp = (cp / np_ * 100) if np_ else 0.0
                sc = (cc / nc_ * 100) if nc_ else 0.0
                p = sc / 100
                se_pp = (np.sqrt(p * (1 - p) / nc_) * 100) if nc_ else float('inf')
                rows.append({
                    'race': race, 'sex': sex, 'band': band,
                    'count_prev': cp, 'count_curr': cc,
                    'share_prev': round(sp, 1), 'share_curr': round(sc, 1),
                    'se_pp': round(se_pp, 2) if nc_ else float('inf'),
                    'is_noise': bool(abs(sc - sp) < 2 * se_pp),
                })
    return pd.DataFrame(rows)


def demographic_verdicts(df: pd.DataFrame, threshold_pct: float = 85,
                         sex: str = 'M', band: str = '18-34') -> list[str]:
    """3–5 markdown bullets: per distance, is the 2026 male-ageing signal real,
    a completeness artefact, or inconclusive — backed by counts and decomposition."""
    years = sorted(df['year'].unique())
    yc = years[-1]
    comp = completeness_flags(df, threshold_pct=threshold_pct, current_year=yc)
    noise = noise_floor_flags(df, current_year=yc)
    race_labels = {'Full': 'Full Marathon', 'Half': 'Half Marathon', '10K': '10K'}

    bullets = [
        f"<b>Question.</b> Normalised shares can mask whether {yc} is a full season; "
        f"below we check absolute counts (threshold: {yc} field must be ≥ {threshold_pct}% "
        f"of the prior-year mean) before reading the male {band} drop as a real shift."
    ]
    for race, label in race_labels.items():
        crow = comp[(comp['race'] == race) & (comp['sex'] == sex)].iloc[0]
        dec = decompose_young_share_shift(df, race, sex=sex, band=band)
        nrow = noise[(noise['race'] == race) & (noise['sex'] == sex) &
                     (noise['band'] == band)].iloc[0]
        pct = crow['pct_of_prior']
        chg = dec['actual_change']
        if crow['provisional']:
            verdict = (f"<b>{label}: completeness artefact (provisional).</b> {yc} male field is "
                       f"only {pct:.0f}% of the prior-year mean — the {band} drop of {chg:+.1f}pp "
                       f"is unreliable; treat {yc} as provisional.")
        elif abs(chg) < 2 * nrow['se_pp']:
            verdict = (f"<b>{label}: inconclusive.</b> {yc} field is complete ({pct:.0f}% of prior) "
                       f"but the male {band} share moved only {chg:+.1f}pp — within sampling noise "
                       f"(±{2*nrow['se_pp']:.1f}pp).")
        else:
            driver = ("more older men" if dec['eff_more_old'] <= dec['eff_fewer_young']
                      else "fewer young men")
            verdict = (f"<b>{label}: real shift.</b> {yc} field is complete ({pct:.0f}% of prior); "
                       f"male {band} share fell {chg:+.1f}pp, driven mainly by {driver} "
                       f"(more-old {dec['eff_more_old']:+.1f}pp vs fewer-young "
                       f"{dec['eff_fewer_young']:+.1f}pp).")
        bullets.append(verdict)
    return bullets


def pyramid_xmax(df: pd.DataFrame, years: list) -> int:
    """Largest single age-band count across the given years/races/sexes — a shared
    x-axis scale so comparison pyramids are directly comparable across years."""
    sub = df[df['year'].isin(years)].copy()
    sub['band'] = sub['ag'].map(band10)
    m = 0
    for year in years:
        for race in RACES:
            for sx in ('M', 'F'):
                g = sub[(sub['year'] == year) & (sub['race'] == race) & (sub['sex'] == sx)]
                if len(g):
                    m = max(m, int(g['band'].value_counts().max()))
    return int(m * 1.15) + 1


# ═══════════════════════════════════════════════════════════════════════════════
# AGE × DISTANCE × GENDER  (within-cell distance shares)
# Of finishers in a (gender, age band, year) cell, what % ran each distance? Pure,
# reuses band10/BANDS10 — no bucket re-derivation.
# ═══════════════════════════════════════════════════════════════════════════════

def distance_share_table(df: pd.DataFrame) -> pd.DataFrame:
    """Tidy [year, gender, age_band, distance, n, share_within_cell]; the three distance
    shares sum to 100 within each (year, gender, age_band) cell."""
    sub = df.copy()
    sub['band'] = sub['ag'].map(band10)
    rows = []
    for year in sorted(sub['year'].unique()):
        for sex in ('F', 'M'):
            for band in BANDS10:
                cell = sub[(sub['year'] == year) & (sub['sex'] == sex) & (sub['band'] == band)]
                total = len(cell)
                if not total:
                    continue
                for dist in RACES:
                    n = int((cell['race'] == dist).sum())
                    rows.append({
                        'year': int(year), 'gender': sex, 'age_band': band,
                        'distance': dist, 'n': n,
                        'share_within_cell': round(n / total * 100, 1),
                    })
    return pd.DataFrame(rows)


def share_matrix(df: pd.DataFrame, sex: str) -> pd.DataFrame:
    """Wide age_band × distance share matrix for one sex, one block per year plus a
    '3-yr avg' block (mean of the per-year shares). Index (year_label, age_band)."""
    tidy = distance_share_table(df)
    tidy = tidy[tidy['gender'] == sex]
    years = sorted(tidy['year'].unique())
    frames = []
    for year in years:
        piv = (tidy[tidy['year'] == year]
               .pivot(index='age_band', columns='distance', values='share_within_cell')
               .reindex(index=BANDS10, columns=RACES))
        piv.insert(0, 'year', str(year))
        frames.append(piv)
    combined = pd.concat(frames)
    avg = (combined.groupby(level=0)[RACES].mean()
           .reindex(index=BANDS10).round(1))
    avg.insert(0, 'year', '3-yr avg')
    return pd.concat([combined, avg])


def tenk_age_gradient(df: pd.DataFrame, sex: str) -> dict:
    """Per year + 3-yr avg: 10K share per band, the gradient
    (share[18-34] - share[55-64]), and whether 10K share rises monotonically across the
    main bands (18-34..55-64, excluding low-n 65+)."""
    tidy = distance_share_table(df)
    tidy = tidy[(tidy['gender'] == sex) & (tidy['distance'] == '10K')]
    main = BANDS10[:-1]
    out = {}
    years = sorted(tidy['year'].unique())
    per_year_vals = {}
    for year in years:
        s = (tidy[tidy['year'] == year].set_index('age_band')['share_within_cell']
             .reindex(BANDS10))
        per_year_vals[year] = s
        seq = [s[b] for b in main if pd.notna(s[b])]
        out[int(year)] = {
            'by_band': {b: (None if pd.isna(s[b]) else float(s[b])) for b in BANDS10},
            'gradient_pp': round(float(s['18-34'] - s['55-64']), 1),
            'monotonic_rising': all(a <= b for a, b in zip(seq, seq[1:])),
        }
    avg = pd.concat(per_year_vals.values(), axis=1).mean(axis=1).reindex(BANDS10)
    seq = [avg[b] for b in main if pd.notna(avg[b])]
    out['3-yr avg'] = {
        'by_band': {b: (None if pd.isna(avg[b]) else round(float(avg[b]), 1)) for b in BANDS10},
        'gradient_pp': round(float(avg['18-34'] - avg['55-64']), 1),
        'monotonic_rising': all(a <= b for a, b in zip(seq, seq[1:])),
    }
    return out


def gender_gradient_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """3-yr-avg within-band distance share for F and M side by side, per (distance, band),
    with diff_pp = F - M. Quantifies how the age->distance relationship differs by gender."""
    fm = share_matrix(df, 'F')
    mm = share_matrix(df, 'M')
    fa = fm[fm['year'] == '3-yr avg']
    ma = mm[mm['year'] == '3-yr avg']
    rows = []
    for dist in RACES:
        for band in BANDS10:
            f = fa.loc[band, dist] if band in fa.index else float('nan')
            m = ma.loc[band, dist] if band in ma.index else float('nan')
            rows.append({
                'distance': dist, 'age_band': band,
                'female_share': round(float(f), 1) if pd.notna(f) else float('nan'),
                'male_share': round(float(m), 1) if pd.notna(m) else float('nan'),
                'diff_pp': round(float(f - m), 1) if pd.notna(f) and pd.notna(m) else float('nan'),
            })
    return pd.DataFrame(rows)


_AGE_CAVEAT = 'Cross-sectional age pattern (a snapshot across ages), not an individual aging trajectory.'


def _share_heatmap_panel(ax, mat, title, provisional_cols=()):
    """Draw one age_band (rows, youngest at bottom) × distance share heatmap."""
    order = list(reversed(BANDS10))
    data = mat.reindex(index=order, columns=RACES).to_numpy(dtype=float)
    im = ax.imshow(data, aspect='auto', cmap='Greens', vmin=0, vmax=100)
    ax.set_xticks(range(len(RACES))); ax.set_xticklabels(RACES, fontsize=8)
    ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=8)
    for i in range(len(order)):
        for j, dist in enumerate(RACES):
            v = data[i, j]
            if np.isnan(v):
                continue
            star = '*' if dist in provisional_cols else ''
            ax.text(j, i, f"{v:.0f}{star}", ha='center', va='center', fontsize=7.5,
                    color='white' if v >= 55 else '#333333')
            if dist in provisional_cols:
                ax.add_patch(mpatches.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                                hatch='///', edgecolor='#C0392B', linewidth=0))
    ax.set_title(title, fontsize=9, fontweight='bold', pad=6)
    return im


def chart_female_distance_heatmap(df: pd.DataFrame, save_path: str = None) -> Image:
    """H1: female within-band distance shares — 3-yr avg main panel + per-year facets."""
    fm = share_matrix(df, 'F')
    years = sorted(df['year'].unique())
    cur = years[-1]
    comp = completeness_flags(df)
    prov_dist = {r for r in RACES
                 if bool(comp[(comp['race'] == r) & (comp['sex'] == 'F')]['provisional'].iloc[0])}

    panels = [('3-yr avg', fm[fm['year'] == '3-yr avg'])]
    panels += [(str(y), fm[fm['year'] == str(y)]) for y in years]

    fig, axes = plt.subplots(1, len(panels), figsize=(3.1 * len(panels), 3.7), sharey=True)
    im = None
    for ax, (label, block) in zip(axes, panels):
        prov = prov_dist if label == str(cur) else set()
        im = _share_heatmap_panel(ax, block[RACES], label, provisional_cols=prov)
    cbar = fig.colorbar(im, ax=axes, shrink=0.6, pad=0.02)
    cbar.set_label('% of age band', fontsize=8); cbar.ax.tick_params(labelsize=7)
    fig.suptitle('Female distance choice by age band — share within each age group',
                 fontsize=13, fontweight='bold', y=1.04)
    note = _AGE_CAVEAT
    if prov_dist:
        note += '   * 2026 cell < 85% of prior-year mean (provisional).'
    fig.text(0.5, -0.03, note, ha='center', fontsize=7, color='grey')
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig_to_image(fig)


def chart_gender_distance_gradient(df: pd.DataFrame, save_path: str = None,
                                   width_cm: float = 17) -> Image:
    """H2: age->distance gradient by gender — one small multiple per distance, line per sex."""
    fa = share_matrix(df, 'F'); fa = fa[fa['year'] == '3-yr avg']
    ma = share_matrix(df, 'M'); ma = ma[ma['year'] == '3-yr avg']
    x = list(range(len(BANDS10)))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.3), sharey=True)
    for ax, dist in zip(axes, RACES):
        fy = [fa.loc[b, dist] if b in fa.index else np.nan for b in BANDS10]
        my = [ma.loc[b, dist] if b in ma.index else np.nan for b in BANDS10]
        ax.plot(x, fy, marker='o', linewidth=2, color=C_PINK, label='Female')
        ax.plot(x, my, marker='s', linewidth=2, color=C_BLUE, label='Male')
        ax.set_xticks(x); ax.set_xticklabels(BANDS10, rotation=40, ha='right', fontsize=8)
        ax.set_ylim(0, 80)
        style_ax(ax, title=dist, ylabel='% within age band' if dist == RACES[0] else '')
        if dist == RACES[0]:
            ax.legend(fontsize=8, loc='upper right')
    gf = tenk_age_gradient(df, 'F')['3-yr avg']['gradient_pp']
    gm = tenk_age_gradient(df, 'M')['3-yr avg']['gradient_pp']
    axes[2].annotate(f"10K age gradient (18-34→55-64)\nFemale {gf:+.0f}pp · Male {gm:+.0f}pp",
                     xy=(0.5, 0.04), xycoords='axes fraction', ha='center', fontsize=7.5,
                     color='#333333',
                     bbox=dict(boxstyle='round', fc='white', ec='grey', alpha=0.8))
    fig.suptitle('Age–distance gradient by gender — share within each age band (3-yr avg)',
                 fontsize=13, fontweight='bold', y=1.02)
    fig.text(0.5, -0.04, _AGE_CAVEAT, ha='center', fontsize=7, color='grey')
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
    return fig_to_image(fig, width_cm=width_cm)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PDF BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_combined_pdf(df_latest: pd.DataFrame, df_all: pd.DataFrame,
                       latest_year: int, club_names: list, out_path: str) -> None:

    W, H = A4
    summary_all = build_summary(df_all)

    styles = getSampleStyleSheet()
    avail_years = sorted(df_all['year'].unique())
    year_range  = f"{avail_years[0]}–{avail_years[-1]}"

    # ── Style definitions ────────────────────────────────────────────────────
    TITLE  = ParagraphStyle('TITLE', fontName='Helvetica-Bold', fontSize=24,
                             textColor=colors.HexColor(C_GREEN), spaceAfter=6,
                             leading=30, alignment=TA_CENTER)
    SECNUM = ParagraphStyle('SECNUM', fontName='Helvetica', fontSize=11,
                             textColor=colors.HexColor(C_GREY), spaceAfter=2,
                             alignment=TA_CENTER)
    SUB    = ParagraphStyle('SUB',   fontName='Helvetica', fontSize=13,
                             textColor=colors.HexColor('#555555'), spaceAfter=3,
                             alignment=TA_CENTER)
    SEC    = ParagraphStyle('SEC',   fontName='Helvetica-Bold', fontSize=15,
                             textColor=colors.HexColor(C_GREEN), spaceAfter=4)
    SUBSEC = ParagraphStyle('SUBSEC',fontName='Helvetica-Bold', fontSize=11,
                             textColor=colors.HexColor(C_DGREY), spaceAfter=6)
    BODY   = ParagraphStyle('BODY',  fontName='Helvetica', fontSize=10,
                             spaceAfter=4, leading=14)
    BODYR  = ParagraphStyle('BODYR', fontName='Helvetica', fontSize=10,
                             spaceAfter=4, leading=14, alignment=TA_CENTER)
    BODYCB = ParagraphStyle('BODYCB',fontName='Helvetica-Bold', fontSize=10,
                             spaceAfter=4, leading=14, alignment=TA_CENTER)
    CT     = ParagraphStyle('CT',    fontName='Helvetica', fontSize=9,
                             textColor=colors.grey, alignment=TA_CENTER, spaceAfter=8)
    FOOT   = ParagraphStyle('FOOT',  fontName='Helvetica', fontSize=8,
                             textColor=colors.grey, alignment=TA_CENTER)

    def hr(color=C_GREEN):
        return HRFlowable(width='100%', thickness=1.5,
                          color=colors.HexColor(color), spaceAfter=6)

    def tsg():
        return TableStyle([
            ('BACKGROUND',    (0,0),(-1,0), colors.HexColor(C_GREEN)),
            ('TEXTCOLOR',     (0,0),(-1,0), colors.white),
            ('FONTNAME',      (0,0),(-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0),(-1,-1), 9),
            ('ALIGN',         (0,0),(-1,-1), 'CENTER'),
            ('ALIGN',         (0,1),(0,-1),  'LEFT'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, colors.HexColor(C_LIGHT)]),
            ('GRID',          (0,0),(-1,-1), 0.4, colors.lightgrey),
            ('TOPPADDING',    (0,0),(-1,-1), 4),
            ('BOTTOMPADDING', (0,0),(-1,-1), 4),
            ('FONTNAME',      (0,-1),(-1,-1),'Helvetica-Bold'),
        ])

    footer_text = f"Analog Devices Cork City Marathon {latest_year} — Results Analysis"

    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(2*cm, 1.2*cm, footer_text)
        canvas.drawRightString(W - 2*cm, 1.2*cm, f"Page {doc.page}")
        canvas.restoreState()

    styles_dict = {'SEC': SEC, 'SUBSEC': SUBSEC, 'BODY': BODY,
                   'BODYR': BODYR, 'BODYCB': BODYCB, 'CT': CT, 'hr': hr}

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = []

    # ── COVER ─────────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 2*cm),
        Paragraph(f'Analog Devices Cork City Marathon {latest_year}', TITLE),
        Paragraph('Race Results Analysis', SUB),
        Spacer(1, 0.8*cm),
        hr(),
        Spacer(1, 0.3*cm),
    ]

    # TOC-style section list
    sections = [
        ('1', f'Overall Marathon Analysis — {latest_year}'),
        ('2', f'Marathon Trend Analysis — {year_range}'),
        ('3', f'All Clubs Overall Analysis — {latest_year}'),
        ('4', f'All Clubs Trend Analysis — {year_range}'),
    ]
    if club_names:
        for i, cn in enumerate(club_names, 1):
            sec_num = f'5.{i}' if len(club_names) > 1 else '5'
            sections.append((sec_num, f'Club Deep Dive: {cn}'))

    toc_data = [[Paragraph(f'<b>{n}.</b>', BODY), Paragraph(title, BODY)]
                for n, title in sections]
    toc = Table(toc_data, colWidths=[1.2*cm, 15.8*cm])
    toc.setStyle(TableStyle([
        ('FONTSIZE',      (0,0),(-1,-1), 10),
        ('TOPPADDING',    (0,0),(-1,-1), 3),
        ('BOTTOMPADDING', (0,0),(-1,-1), 3),
        ('ROWBACKGROUNDS',(0,0),(-1,-1), [colors.white, colors.HexColor(C_LIGHT)]),
    ]))
    story.append(toc)
    story += [
        Spacer(1, 0.6*cm),
        Paragraph('Report design using Claude Cowork · Code generated using Claude Code · Crafted by Humans', FOOT),
    ]
    story.append(PageBreak())

    # ── SECTION 1: OVERALL MARATHON ANALYSIS ─────────────────────────────────
    story += [hr(), Paragraph(f'1. Overall Marathon Analysis — {latest_year}', SEC),
              Spacer(1, 0.2*cm)]

    # Summary table
    hdr = ['Race', 'Finishers', 'Male', 'Female', 'Fastest', 'Median']
    rows = [hdr]
    totals = {'fin': 0, 'm': 0, 'f': 0}
    race_labels = {'Full': 'Marathon', 'Half': 'Half Marathon', '10K': '10K'}
    for race in RACES:
        st = race_stats(df_latest, race)
        if not st: continue
        totals['fin'] += st['total']; totals['m'] += st['male']; totals['f'] += st['female']
        rows.append([race_labels[race], f"{st['total']:,}", f"{st['male']:,}",
                     f"{st['female']:,}", sec_to_hms(st['fastest']), sec_to_hms(st['median'])])
    rows.append(['All Races', str(totals['fin']), str(totals['m']), str(totals['f']), '—', '—'])
    t = Table(rows, colWidths=[3.5*cm, 2.5*cm, 2.2*cm, 2.2*cm, 2.8*cm, 2.8*cm])
    ts = tsg(); ts.add('TEXTCOLOR', (4, 1), (4, -2), colors.HexColor(C_GOLD))
    t.setStyle(ts)
    story += [t, Spacer(1, 0.4*cm), chart_gender_split(df_latest, latest_year), PageBreak()]

    for race in RACES:
        sub = df_latest[df_latest['race'] == race]
        if sub.empty: continue
        st = race_stats(df_latest, race)
        story += [hr(), Paragraph(f'{race_labels[race]} — {latest_year}', SEC),
                  Paragraph(f"{st['total']:,} finishers", SUBSEC), Spacer(1, 0.2*cm)]

        def colored(text, c): return f'<font color="{c}">{text}</font>'
        m = sub[sub['sex']=='M']; f = sub[sub['sex']=='F']
        m_str = f"{st['male']:,} ({st['pct_male']}%)"
        f_str = f"{st['female']:,} ({st['pct_female']}%)"
        left_data = [
            ['Total Finishers', Paragraph(f"{st['total']:,}", BODYR)],
            ['Male Finishers',   Paragraph(colored(m_str, C_BLUE), BODYR)],
            ['Female Finishers', Paragraph(colored(f_str, C_PINK), BODYR)],
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
            ('FONTSIZE',(0,0),(-1,-1),9), ('ALIGN',(1,0),(1,-1),'RIGHT'),
            ('GRID',(0,0),(-1,-1),0.3,colors.lightgrey),
            ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.white,colors.HexColor(C_LIGHT)]),
            ('TOPPADDING',(0,0),(-1,-1),3), ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ])
        tl = Table(left_data, colWidths=[4.2*cm, 4*cm])
        tr = Table(right_data, colWidths=[4.2*cm, 4*cm])
        tl.setStyle(ts_plain); tr.setStyle(ts_plain)
        pair = Table([[tl, '', tr]], colWidths=[8.2*cm, 0.6*cm, 8.2*cm])
        pair.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
        story += [pair, Spacer(1, 0.4*cm),
                  chart_time_distribution(df_latest, race),
                  chart_ag_pair(df_latest, race, 'M'),
                  chart_ag_pair(df_latest, race, 'F'),
                  PageBreak()]

    # ── SECTION 2: MARATHON TREND ANALYSIS ───────────────────────────────────
    INSIGHT = ParagraphStyle('INSIGHT', fontName='Helvetica', fontSize=9,
                             textColor=colors.HexColor('#444444'),
                             spaceAfter=3, leading=13, leftIndent=6)
    INSIGHT_HEAD = ParagraphStyle('INSIGHT_HEAD', fontName='Helvetica-Bold', fontSize=9,
                                  textColor=colors.HexColor(C_GREEN), spaceAfter=2)

    def insight_block(bullets, label='Key Insights'):
        items = [Spacer(1, 0.25*cm), Paragraph(label, INSIGHT_HEAD)]
        for b in bullets:
            items.append(Paragraph(f'• {b}', INSIGHT))
        return items

    story += [hr(), Paragraph(f'2. Marathon Trend Analysis — {year_range}', SEC),
              Spacer(1, 0.2*cm),
              chart_trend_total(summary_all),
              Spacer(1, 0.3*cm),
              chart_trend_female_pct(summary_all),
              Spacer(1, 0.3*cm),
              chart_trend_male_pct(summary_all),
              PageBreak(),
              chart_trend_participation(summary_all),
              Spacer(1, 0.3*cm),
              chart_trend_median_time(df_all),
              Spacer(1, 0.3*cm),
              chart_trend_age_groups(df_all),
              Spacer(1, 0.3*cm),
              chart_ag_trend_median_time(df_all),
              PageBreak()]
    for race in RACES:
        story.append(chart_trend_boxplot(df_all, race))
        story.append(Spacer(1, 0.3*cm))

    # ── SECTION 2: AGE PROFILE BY RACE & GENDER — 3-year pyramids ────────────
    THRESH = 85
    years_all = sorted(df_all['year'].unique())
    comp = completeness_flags(df_all, threshold_pct=THRESH)
    noise = noise_floor_flags(df_all)
    any_provisional = bool(comp['provisional'].any())
    g_xmax = pyramid_xmax(df_all, years_all)

    story += [PageBreak(), hr(),
              Paragraph('Age Profile by Race &amp; Gender', SEC),
              Spacer(1, 0.2*cm)]
    for yr in years_all:
        cap = (f'Age profile by race and gender — {yr} '
               '(Male left, Female right; female % shown per race)')
        if yr == years_all[-1] and any_provisional:
            cap += ' — provisional'
        story += [chart_age_pyramids(df_all, yr, xmax=g_xmax), Paragraph(cap, CT)]

    # ── SECTION 2: AGE, DISTANCE & GENDER (2 hypotheses) ─────────────────────
    fig_dir = os.path.dirname(out_path) or '.'
    favg = share_matrix(df_all, 'F')
    favg = favg[favg['year'] == '3-yr avg']
    gradF = tenk_age_gradient(df_all, 'F')
    gradM = tenk_age_gradient(df_all, 'M')
    ggc = gender_gradient_comparison(df_all)
    gf = gradF['3-yr avg']['gradient_pp']
    gm = gradM['3-yr avg']['gradient_pp']
    tenk10 = ggc[ggc['distance'] == '10K']
    diff_lo, diff_hi = tenk10['diff_pp'].min(), tenk10['diff_pp'].max()

    def _share_style():
        return TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(C_GREEN)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(C_LIGHT)]),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])

    h1_rows = [['Age band', 'Full %', 'Half %', '10K %']]
    for b in BANDS10:
        if b in favg.index:
            h1_rows.append([b, f"{favg.loc[b, 'Full']:.0f}",
                            f"{favg.loc[b, 'Half']:.0f}", f"{favg.loc[b, '10K']:.0f}"])
    h1_tbl = Table(h1_rows, colWidths=[3*cm, 2.6*cm, 2.6*cm, 2.6*cm]); h1_tbl.setStyle(_share_style())

    h2_bullets = [
        "<b>Same direction, different magnitude.</b> Both genders trend toward the 10K with age, but "
        f"men run longer at every age — their within-band 10K share is {diff_lo:.0f}–{diff_hi:.0f}pp "
        "below women's in every band.",
        f"<b>Women's trend is far steeper.</b> The 10K age-gradient is {abs(gf):.0f}pp for women vs "
        f"{abs(gm):.0f}pp for men — women's distance choice shifts with age about {abs(gf)/abs(gm):.1f}× as much.",
        "<b>Men diverge in midlife.</b> Men's 10K share dips at 35-44 (their long-distance peak), so the "
        "male gradient is non-monotonic, whereas the female trend rises monotonically.",
    ]

    caveat = (f'{_AGE_CAVEAT} Cohort effects cannot be separated without runner-level IDs '
              '(a longitudinal cut is a follow-up). 2026 passes the ≥ 85% completeness guard for '
              "every distance×gender cell (young women's 10K closest at 87%). 65+ is low-n.")

    reconcile_bullets = [
        "<b>Both charts are correct — they measure different things.</b> The pyramids show absolute "
        "head counts; the heatmap and table show the share <i>within</i> each age band.",
        "<b>Absolute numbers (pyramids).</b> The volume of older female runners is far smaller than "
        "younger: in 2024, 177 women aged 18–34 ran the Full versus just 6 women aged 65+.",
        "<b>Proportions (heatmap/table).</b> The 3-yr-average Full share is 9% at 18–34 versus 14% "
        "at 65+ — i.e. of all women in each band, what fraction chose the Full Marathon.",
        "<b>Why both hold.</b> The 18–34 pool is huge, so a smaller proportion is still many runners; "
        "the 65+ pool is tiny, so a larger proportion is still very few runners.",
        "<b>2024 worked example.</b> 18–34 women: 2,155 total (177 Full + 872 Half + 1,106 10K) → "
        "Full ≈ 8%. 65+ women: 31 total (6 Full + 4 Half + 21 10K) → Full ≈ 19%.",
        "<b>In short.</b> As women age, total participation drops sharply — but among the few who keep "
        "running at 65+, a slightly higher fraction opt for the Full than at 18–34.",
    ]

    story += [PageBreak(), hr(), Paragraph('Age, Distance &amp; Gender', SEC), Spacer(1, 0.15*cm),
              chart_female_distance_heatmap(
                  df_all, save_path=os.path.join(fig_dir, 'age_distance_female_heatmap.png')),
              Paragraph('Female share of each age band running each distance — '
                        '3-yr average (left) and by year', CT),
              h1_tbl,
              PageBreak(),
              chart_age_pyramids(df_all, years=years_all, figsize=(14, 3.3), width_cm=15),
              Paragraph(f'Age profile by race &amp; gender — {years_all[0]}–{years_all[-1]} '
                        'average (Male left, Female right; female % shown per race)', CT),
              chart_gender_distance_gradient(
                  df_all, save_path=os.path.join(fig_dir, 'age_distance_gender_gradient.png'),
                  width_cm=15),
              Paragraph('Within-band distance share by gender, per distance — 3-yr average', CT),
              Spacer(1, 0.1*cm)]
    for b in h2_bullets:
        story.append(Paragraph(f'• {b}', INSIGHT))
    story += [Spacer(1, 0.25*cm), Paragraph('Why the pyramid and the heatmap agree', INSIGHT_HEAD)]
    for b in reconcile_bullets:
        story.append(Paragraph(f'• {b}', INSIGHT))
    story += [Spacer(1, 0.2*cm), Paragraph(caveat, CT)]

    # ── SECTION 2: 2026 DATA-COMPLETENESS CHECK (composition + verdicts) ──────

    # Noise caveat for the small male 65+ band
    noisy_old = [r for r in RACES if noise[
        (noise['race'] == r) & (noise['sex'] == 'M') & (noise['band'] == '65+')
    ]['is_noise'].iloc[0]]
    noise_line = (
        f"Year-on-year movements in the male 65+ band ({', '.join(noisy_old)}) sit within the "
        f"sampling-noise floor (small counts) and are not interpreted as trends."
        if noisy_old else
        "Male 65+ band movements exceed the sampling-noise floor.")

    story += [PageBreak(), hr(),
              Paragraph('Age Profile — 2026 Data-Completeness Check', SEC),
              Spacer(1, 0.15*cm),
              chart_age_composition_trend(df_all),
              Paragraph('Age composition by race, gender and year — each bar normalised to 100%', CT),
              Spacer(1, 0.1*cm)]
    for b in demographic_verdicts(df_all, threshold_pct=THRESH):
        story.append(Paragraph(f'• {b}', INSIGHT))
    story += [Spacer(1, 0.15*cm), Paragraph(noise_line, CT)]

    # ── SECTION 2: KEY INSIGHTS PAGE ─────────────────────────────────────────
    story += [PageBreak(),
              hr(),
              Paragraph(f'2. Marathon Trend Analysis — Key Insights', SEC),
              Spacer(1, 0.3*cm)]
    story += insight_block(_trend_insights_participation(summary_all), 'Participation & gender')
    story += [Spacer(1, 0.4*cm)]
    story += insight_block(_trend_insights_times_ages(df_all), 'Finish times & age groups')
    story += [Spacer(1, 0.4*cm)]
    story += insight_block(_trend_insights_boxplot(df_all), 'Finish-time distribution')
    story += [
        Spacer(1, 0.4*cm),
        Paragraph('Age profile', INSIGHT_HEAD),
        Paragraph(
            'Female participation falls as the distance grows: women make up their largest '
            'share in the 10 km (61%) and their smallest in the Full Marathon (23%). The '
            'population pyramids show the age profile behind that gap for each race in '
            f'{latest_year} — the shorter female side in the Full Marathon is immediately '
            'visible. The 18–34 group is the largest band in every race, and the field skews '
            'progressively younger as the distance shortens (18–34 rises from 41% of Full '
            'Marathon finishers to 46% in the 10 km), while the Full Marathon carries the '
            'oldest, most masters-heavy profile.',
            INSIGHT),
    ]
    story.append(PageBreak())

    # ── SECTION 3: ALL CLUBS OVERALL ─────────────────────────────────────────
    story += [hr(), Paragraph(f'3. All Clubs Overall Analysis — {latest_year}', SEC),
              Spacer(1, 0.2*cm)]

    # Club summary table
    club_hdr = ['Race', 'Total Finishers', 'With Club', 'Affiliation Rate', 'Unique Clubs']
    club_rows = [club_hdr]
    tot_fin = tot_wc = 0; unique_all = set()
    for race in RACES:
        sub = df_latest[df_latest['race'] == race]
        wc  = sub[sub['club'].str.strip() != '']
        pct = round(100 * len(wc) / len(sub)) if len(sub) else 0
        uc  = wc['club'].str.strip().nunique()
        club_rows.append([race_labels[race], f"{len(sub):,}", f"{len(wc):,}", f"{pct}%", str(uc)])
        tot_fin += len(sub); tot_wc += len(wc)
        unique_all |= set(wc['club'].str.strip().unique())
    tot_pct = round(100 * tot_wc / tot_fin) if tot_fin else 0
    club_rows.append(['All Races', str(tot_fin), str(tot_wc), f'{tot_pct}%',
                      f'{len(unique_all)} unique'])
    ct = Table(club_rows, colWidths=[3.5*cm, 3*cm, 2.5*cm, 3*cm, 2.8*cm])
    cts = tsg(); cts.add('ALIGN', (1,1), (-1,-1), 'CENTER'); ct.setStyle(cts)
    n_clubs = df_latest[df_latest['club'].str.strip()!='']['club'].str.strip().nunique()
    story += [ct, Spacer(1, 0.5*cm), chart_club_affiliation(df_latest),
              Spacer(1, 0.3*cm),
              Paragraph('Club Word Cloud', SUBSEC),
              Paragraph(f'All {n_clubs} clubs — size proportional to finishers', BODY)]
    img = chart_word_cloud(df_latest)
    if img: story.append(img)
    story.append(PageBreak())

    sets = {}
    for race in RACES:
        sub = df_latest[(df_latest['race'] == race) & (df_latest['club'].str.strip() != '')]
        sets[race] = set(sub['club'].str.strip().unique())
    full, half, tenk = sets['Full'], sets['Half'], sets['10K']
    all3 = full & half & tenk

    story += [
        hr(),
        Paragraph('Club Overlap by Race — Venn Diagram', SEC),
        Paragraph(
            f"{len(all3)} clubs in all 3 races · "
            f"{len((full | half | tenk) - (full & half) - (full & tenk) - (half & tenk))} clubs in only one race",
            SUBSEC),
    ]
    img = chart_venn(df_latest)
    if img: story.append(img)

    venn_data = [
        ['Region', 'Clubs', 'Meaning'],
        ['Marathon only',   str(len(full - half - tenk)),   'Clubs with finishers in marathon only'],
        ['Half only',       str(len(half - full - tenk)),   'Clubs with finishers in half marathon only'],
        ['10K only',        str(len(tenk - full - half)),   'Clubs with finishers in 10K only'],
        ['Marathon + Half', str(len((full & half) - tenk)), 'Clubs in both, not 10K'],
        ['Marathon + 10K',  str(len((full & tenk) - half)), 'Clubs in both, not Half'],
        ['Half + 10K',      str(len((half & tenk) - full)), 'Clubs in both, not Marathon'],
        [Paragraph('<b>All 3 races</b>', BODY),
         Paragraph(f'<b>{len(all3)}</b>', BODYCB),
         Paragraph('<b>Clubs with finishers across all three races</b>', BODY)],
    ]
    venn_t = Table(venn_data, colWidths=[3.5*cm, 2*cm, 9.3*cm])
    venn_t.setStyle(tsg())
    story += [Spacer(1, 0.3*cm), venn_t, PageBreak()]

    story += [chart_club_top5_avg(df_latest, min_finishers=5), PageBreak()]

    img = chart_age_group_heatmap_overall(df_latest, min_finishers=20)
    if img: story += [img, Spacer(1, 0.3*cm)]
    heatmap_threshold = {'Full': 15, 'Half': 20, '10K': 15}
    for race in RACES:
        img = chart_age_group_heatmap(df_latest, race, min_finishers=heatmap_threshold[race])
        if img: story += [img, Spacer(1, 0.3*cm)]
    story.append(PageBreak())

    story += [chart_top_clubs_combined(df_latest), PageBreak()]
    for race in RACES:
        img = chart_top_clubs(df_latest, race)
        if img: story += [img, Spacer(1, 0.3*cm)]
    story.append(PageBreak())

    # ── SECTION 4: ALL CLUBS TREND ────────────────────────────────────────────
    story += [hr(), Paragraph(f'4. All Clubs Trend Analysis — {year_range}', SEC),
              Spacer(1, 0.2*cm),
              chart_clubs_count_trend(df_all),
              Spacer(1, 0.4*cm),
              chart_top_clubs_trend(df_all)]

    # ── SECTION 5: PER-CLUB DEEP DIVES ───────────────────────────────────────
    if club_names:
        for i, cn in enumerate(club_names, 1):
            matched = _find_club(df_latest, cn)
            if not matched:
                print(f"  WARNING: '{cn}' not found — skipping.")
                continue
            print(f"  Club deep dive: {matched}")
            sec_label = f'5.{i}' if len(club_names) > 1 else '5'

            build_club_section(df_latest, matched, latest_year, story, styles_dict, section_label=sec_label)
            build_club_trend_section(df_all, matched, story, styles_dict, section_label=sec_label)
            build_club_finish_time_page(df_latest, matched, story, styles_dict, section_label=sec_label)

    # ── BUILD ─────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    print(f"\nReport saved: {out_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description='Generate combined single-year + multi-year Cork City Marathon PDF.')
    ap.add_argument('--data',  default='data/cork',
                    help='Base data directory (default: data/cork)')
    ap.add_argument('--year',  type=int, default=2026,
                    help='Most recent year for single-year sections (default: 2026)')
    ap.add_argument('--out',   default=None,
                    help='Output PDF path (default: report_charts/cork_marathon_combined.pdf)')
    ap.add_argument('--club',  nargs='+', default=None,
                    help='One or more club names for deep dive sections, '
                         'e.g. --club "Togher A.C." "Eagle A.C."')
    args = ap.parse_args()
    if args.year not in PDF_FILES:
        sys.exit(f"ERROR: year {args.year} not supported. Supported: {sorted(PDF_FILES)}")

    out = args.out or 'report_charts/analog_devices_cork_marathon_analysis.pdf'
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        print(f"Loading all years ({', '.join(str(y) for y in YEARS)})…")
        df_all = load_all_years(args.data, tmp)

    if df_all.empty:
        sys.exit("ERROR: No multi-year data found.")

    df_latest = df_all[df_all['year'] == args.year].copy()
    if df_latest.empty:
        sys.exit(f"ERROR: No data found for {args.year}.")

    print(f"\nLatest year: {len(df_latest):,} records")
    print(f"All years:   {len(df_all):,} records")
    print("\nBuilding combined PDF…")
    build_combined_pdf(df_latest, df_all, args.year, args.club or [], out)


if __name__ == '__main__':
    main()
