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
  python generate_combined_report.py --club "Togher A.C." "Eagle A.C."
  python generate_combined_report.py --data data/cork --out report_charts/combined.pdf

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
from generate_single_year_report import (
    load_year, sec_to_hms, race_stats, _find_club,
    RACES, DECADES, DECADE_MAP,
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

YEARS = [2024, 2025, 2026]
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
    sub_all['decade'] = sub_all['ag'].map(DECADE_MAP)
    race_labels = {'Full': 'Marathon', 'Half': 'Half\nMarathon', '10K': '10K'}
    col_labels = [race_labels[r] for r in RACES]

    active_decades = [d for d in DECADES
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
                             story: list, styles: dict) -> None:
    """Append multi-year club trend pages to story. No athlete names."""
    SEC, SUBSEC, BODY, HR = (
        styles['SEC'], styles['SUBSEC'], styles['BODY'], styles['hr'])

    sub = df_all[df_all['club'].str.strip() == club_name]
    if sub.empty:
        return

    avail_years = sorted(df_all['year'].unique())
    year_range  = f"{avail_years[0]}–{avail_years[-1]}"

    story.append(PageBreak())
    story.append(HR())
    story.append(Paragraph(f'{club_name} — Trend Analysis {year_range}', SEC))
    story.append(Paragraph(
        f'Year-on-year performance across {len(avail_years)} seasons. '
        'No athlete names used.', SUBSEC))
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
        for sex, name in [('M', 'male'), ('F', 'female')]:
            s = sub[sub['sex'] == sex]['sec']
            if len(s) > 10:
                iqr = s.quantile(0.75) - s.quantile(0.25)
                if sex == 'F':
                    f_iqr = iqr
                else:
                    m_iqr = iqr
        if f_iqr > m_iqr:
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
        for cn in club_names:
            sections.append(('5', f'Club Deep Dive: {cn}'))

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
        Paragraph('Designed with Claude Cowork · Generated in Claude Code · Grafted by a Human', FOOT),
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
        from reportlab.platypus import TableStyle as TS
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

    def insight_block(bullets):
        items = [Spacer(1, 0.25*cm), Paragraph('Key Insights', INSIGHT_HEAD)]
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

    # ── SECTION 2: KEY INSIGHTS PAGE ─────────────────────────────────────────
    story += [PageBreak(),
              hr(),
              Paragraph(f'2. Marathon Trend Analysis — Key Insights', SEC),
              Spacer(1, 0.3*cm)]
    story += insight_block(_trend_insights_participation(summary_all))
    story += [Spacer(1, 0.4*cm)]
    story += insight_block(_trend_insights_times_ages(df_all))
    story += [Spacer(1, 0.4*cm)]
    story += insight_block(_trend_insights_boxplot(df_all))
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
        for cn in club_names:
            matched = _find_club(df_latest, cn)
            if not matched:
                print(f"  WARNING: '{cn}' not found — skipping.")
                continue
            print(f"  Club deep dive: {matched}")

            # 5a — single year
            build_club_section(df_latest, matched, latest_year, story, styles_dict)

            # 5b — multi-year trend
            build_club_trend_section(df_all, matched, story, styles_dict)

            # 5c — finish time analysis + key insights (always last)
            build_club_finish_time_page(df_latest, matched, story, styles_dict)

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

    out = args.out or 'report_charts/analog_devices_cork_marathon_analysis.pdf'
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        print(f"Loading {args.year} data…")
        df_latest = load_year(args.year, args.data, tmp)
        print(f"Loading all years ({', '.join(str(y) for y in YEARS)})…")
        df_all = load_all_years(args.data, tmp)

    if df_latest.empty:
        sys.exit(f"ERROR: No data found for {args.year}.")
    if df_all.empty:
        sys.exit("ERROR: No multi-year data found.")

    print(f"\nLatest year: {len(df_latest):,} records")
    print(f"All years:   {len(df_all):,} records")
    print("\nBuilding combined PDF…")
    build_combined_pdf(df_latest, df_all, args.year, args.club or [], out)


if __name__ == '__main__':
    main()
