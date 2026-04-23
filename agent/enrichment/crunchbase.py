"""
Crunchbase ODM sample lookup.
Expects the dataset at data/crunchbase_odm.csv (Apache 2.0).
Download: github.com/luminati-io/Crunchbase-dataset-samples
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .models import EnrichmentBrief

_ODM_PATH = Path(__file__).parents[2] / "data" / "crunchbase_odm.csv"
_df: Optional[pd.DataFrame] = None


def _load() -> pd.DataFrame:
    global _df
    if _df is None:
        if not _ODM_PATH.exists():
            raise FileNotFoundError(
                f"Crunchbase ODM not found at {_ODM_PATH}. "
                "Download from github.com/luminati-io/Crunchbase-dataset-samples "
                "and place as data/crunchbase_odm.csv"
            )
        _df = pd.read_csv(_ODM_PATH, low_memory=False)
        _df.columns = [c.strip().lower().replace(" ", "_") for c in _df.columns]
    return _df


def lookup(company_name: str) -> Optional[EnrichmentBrief]:
    """Return an EnrichmentBrief for the closest matching company name, or None."""
    df = _load()
    name_col = _detect_name_col(df)
    if name_col is None:
        raise ValueError("Cannot find a 'name' column in the ODM CSV.")

    needle = company_name.lower().strip()
    mask = df[name_col].str.lower().str.strip() == needle
    row = df[mask].head(1)

    if row.empty:
        # fuzzy fallback: contains match
        mask = df[name_col].str.lower().str.contains(needle, na=False)
        row = df[mask].head(1)

    if row.empty:
        return None

    r = row.iloc[0].to_dict()
    return _row_to_brief(r)


def lookup_by_id(crunchbase_id: str) -> Optional[EnrichmentBrief]:
    df = _load()
    id_col = _detect_id_col(df)
    if id_col is None:
        return None
    mask = df[id_col].astype(str).str.strip() == crunchbase_id.strip()
    row = df[mask].head(1)
    if row.empty:
        return None
    return _row_to_brief(row.iloc[0].to_dict())


def sample(n: int = 10) -> list[EnrichmentBrief]:
    """Return n random companies from the ODM."""
    df = _load()
    rows = df.sample(min(n, len(df)))
    return [_row_to_brief(r.to_dict()) for _, r in rows.iterrows()]


def _detect_name_col(df: pd.DataFrame) -> Optional[str]:
    for candidate in ["name", "company_name", "organization_name", "title"]:
        if candidate in df.columns:
            return candidate
    return None


def _detect_id_col(df: pd.DataFrame) -> Optional[str]:
    for candidate in ["uuid", "id", "crunchbase_id", "org_uuid"]:
        if candidate in df.columns:
            return candidate
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


def _row_to_brief(r: dict) -> EnrichmentBrief:
    cols = {k.lower(): v for k, v in r.items()}

    def g(*keys):
        for k in keys:
            if k in cols and pd.notna(cols[k]):
                return cols[k]
        return None

    crunchbase_id = str(g("uuid", "id", "crunchbase_id", "org_uuid") or "unknown")

    return EnrichmentBrief(
        crunchbase_id=crunchbase_id,
        company_name=str(g("name", "company_name", "organization_name") or "Unknown"),
        industry=g("category_list", "industry", "primary_category"),
        size=g("employee_count", "num_employees_enum", "size"),
        location=g("city", "country_code", "region"),
        funding_total_usd=_safe_float(g("total_funding_usd", "funding_total", "total_funding")),
        founded_year=_safe_int(g("founded_on", "founded_year")),
        description=g("short_description", "description"),
        homepage_url=g("homepage_url", "website"),
        last_enriched_at=datetime.now(timezone.utc),
    )


def save_brief(brief: EnrichmentBrief, output_dir: str = ".") -> str:
    path = os.path.join(output_dir, "enrichment_brief.json")
    with open(path, "w") as f:
        f.write(brief.model_dump_json(indent=2))
    return path
