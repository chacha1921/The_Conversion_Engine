"""
layoffs.fyi integration (CC-BY).
Expects dataset at data/layoffs.csv
Download: layoffs.fyi or huggingface.co mirror
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .models import LayoffEvent

_LAYOFFS_PATH = Path(__file__).parents[2] / "data" / "layoffs.csv"
_df: Optional[pd.DataFrame] = None
_WINDOW_DAYS = 120


def _load() -> pd.DataFrame:
    global _df
    if _df is None:
        if not _LAYOFFS_PATH.exists():
            return pd.DataFrame()
        _df = pd.read_csv(_LAYOFFS_PATH, low_memory=False)
        _df.columns = [c.strip().lower().replace(" ", "_") for c in _df.columns]
    return _df


def check(company_name: str) -> Optional[LayoffEvent]:
    """Return the most recent LayoffEvent within 120 days, or None."""
    df = _load()
    if df.empty:
        return None

    name_col = _name_col(df)
    if name_col is None:
        return None

    needle = company_name.lower().strip()
    mask = df[name_col].str.lower().str.strip().str.contains(needle, na=False)
    matches = df[mask].copy()
    if matches.empty:
        return None

    date_col = _date_col(df)
    cutoff = datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)

    if date_col:
        matches[date_col] = pd.to_datetime(matches[date_col], errors="coerce", utc=True)
        matches = matches[matches[date_col] >= cutoff]

    if matches.empty:
        return None

    if date_col:
        matches = matches.sort_values(date_col, ascending=False)

    r = matches.iloc[0]
    event_date = str(r.get(date_col, "")) if date_col else None
    days_ago = None
    if event_date:
        try:
            dt = pd.to_datetime(event_date, utc=True)
            days_ago = (datetime.now(timezone.utc) - dt).days
        except Exception:
            pass

    pct = _safe_float(r.get("percentage_laid_off") or r.get("pct_laid_off"))
    count = _safe_int(r.get("laid_off") or r.get("headcount_lost") or r.get("num_laid_off"))

    return LayoffEvent(
        date=event_date,
        headcount_lost=count,
        pct_cut=pct,
        source=str(r.get("source", "layoffs.fyi")),
        days_ago=days_ago,
    )


def _name_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["company", "company_name", "name"]:
        if c in df.columns:
            return c
    return None


def _date_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["date", "date_added", "layoff_date"]:
        if c in df.columns:
            return c
    return None


def _safe_float(val) -> Optional[float]:
    try:
        return float(val) if pd.notna(val) else None
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    try:
        return int(float(val)) if pd.notna(val) else None
    except (TypeError, ValueError):
        return None
