"""
Full enrichment pipeline.
Runs all enrichment steps and produces the three brief JSON artifacts.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Optional

from .crunchbase import lookup as crunchbase_lookup
from .layoffs import check as layoffs_check
from .leadership import check_sync as leadership_check
from .ai_maturity import RawSignals, score as ai_score
from .job_posts import fetch_job_titles_sync
from .models import (
    EnrichmentBrief,
    HiringSignalBrief,
    CompetitorGapBrief,
    FundingEvent,
    GapPractice,
    PeerScore,
)


def run(
    company_name: str,
    careers_url: Optional[str] = None,
    press_release_url: Optional[str] = None,
    output_dir: str = ".",
) -> tuple[EnrichmentBrief, HiringSignalBrief, CompetitorGapBrief]:
    """
    Run the full enrichment pipeline for a company.
    Returns (enrichment_brief, hiring_signal_brief, competitor_gap_brief).
    Writes JSON files to output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)

    # ── Step 1: Crunchbase firmographics ──────────────────────────────
    brief = crunchbase_lookup(company_name)
    if brief is None:
        brief = EnrichmentBrief(
            crunchbase_id="not-found",
            company_name=company_name,
            last_enriched_at=datetime.now(timezone.utc),
        )

    _write_json(brief.model_dump_json(indent=2), output_dir, "enrichment_brief.json")

    # ── Step 2: Layoff signal ─────────────────────────────────────────
    layoff = layoffs_check(company_name)

    # ── Step 3: Leadership change ─────────────────────────────────────
    leadership = leadership_check(company_name, press_release_url)

    # ── Step 4: Job posts ─────────────────────────────────────────────
    job_titles: list[str] = []
    if careers_url:
        job_titles = fetch_job_titles_sync(careers_url)
    open_role_count = len(job_titles)
    weak_signal = open_role_count < 5

    # ── Step 5: AI maturity scoring ───────────────────────────────────
    signals = RawSignals(
        job_titles=job_titles,
        total_open_roles=open_role_count,
        leadership_titles=[],
        github_ai_repos=0,
        exec_ai_commentary=False,
        ml_stack_tools=[],
        ai_in_strategic_comms=False,
    )
    ai_score_val, ai_confidence, ai_signals = ai_score(signals)

    hiring_brief = HiringSignalBrief(
        company_name=company_name,
        crunchbase_id=brief.crunchbase_id,
        open_role_count=open_role_count,
        weak_signal=weak_signal,
        layoff_event=layoff,
        leadership_change=leadership,
        ai_maturity_score=ai_score_val,
        ai_maturity_confidence=ai_confidence,
        ai_maturity_signals=ai_signals,
        per_signal_confidence={s.signal: (1.0 if s.present else 0.0) for s in ai_signals},
    )
    _write_json(hiring_brief.model_dump_json(indent=2), output_dir, "hiring_signal_brief.json")

    # ── Step 6: Competitor gap brief (population-level, requires ODM) ─
    competitor_brief = _build_gap_brief(company_name, brief, ai_score_val)
    _write_json(competitor_brief.model_dump_json(indent=2), output_dir, "competitor_gap_brief.json")

    return brief, hiring_brief, competitor_brief


def _build_gap_brief(
    company_name: str,
    brief: EnrichmentBrief,
    prospect_score: int,
) -> CompetitorGapBrief:
    """
    Build competitor_gap_brief by scoring peers from the Crunchbase ODM sample.
    Falls back to an empty brief if ODM is unavailable.
    """
    from .crunchbase import sample as crunchbase_sample

    try:
        peers_raw = crunchbase_sample(50)
    except FileNotFoundError:
        return CompetitorGapBrief(
            company_name=company_name,
            crunchbase_id=brief.crunchbase_id,
            sector=brief.industry,
            prospect_ai_maturity=prospect_score,
        )

    # Score each peer with default signals (no web scraping at population level)
    peer_scores: list[PeerScore] = []
    for peer in peers_raw:
        if peer.company_name == company_name:
            continue
        default_signals = RawSignals(
            job_titles=[],
            total_open_roles=0,
            leadership_titles=[],
            github_ai_repos=0,
            exec_ai_commentary=False,
            ml_stack_tools=[],
            ai_in_strategic_comms=False,
        )
        s, _, _ = ai_score(default_signals)
        peer_scores.append(PeerScore(
            company_name=peer.company_name,
            crunchbase_id=peer.crunchbase_id,
            ai_maturity_score=s,
            industry=peer.industry,
        ))

    if not peer_scores:
        return CompetitorGapBrief(
            company_name=company_name,
            crunchbase_id=brief.crunchbase_id,
            sector=brief.industry,
            prospect_ai_maturity=prospect_score,
        )

    scores = [p.ai_maturity_score for p in peer_scores]
    above = sum(1 for s in scores if s > prospect_score)
    percentile = round((1 - above / len(scores)) * 100, 1)

    top_quartile = sorted(peer_scores, key=lambda p: p.ai_maturity_score, reverse=True)
    top_quartile = top_quartile[: max(1, len(top_quartile) // 4)]

    gap_practices: list[GapPractice] = [
        GapPractice(
            practice="Named Head of AI or Chief Scientist on public team page",
            evidence_source="Crunchbase + LinkedIn team pages",
            peers_showing=sum(1 for p in top_quartile if p.ai_maturity_score >= 2),
            prospect_shows=prospect_score >= 2,
        ),
        GapPractice(
            practice="Active AI-adjacent open roles (ML Eng, LLM Eng, Applied Scientist)",
            evidence_source="Public job boards (BuiltIn / Wellfound)",
            peers_showing=sum(1 for p in top_quartile if p.ai_maturity_score >= 1),
            prospect_shows=prospect_score >= 1,
        ),
    ]

    return CompetitorGapBrief(
        company_name=company_name,
        crunchbase_id=brief.crunchbase_id,
        sector=brief.industry,
        prospect_ai_maturity=prospect_score,
        prospect_percentile=percentile,
        top_quartile_peers=top_quartile[:10],
        gap_practices=[g for g in gap_practices if not g.prospect_shows],
    )


def _write_json(content: str, directory: str, filename: str) -> None:
    with open(os.path.join(directory, filename), "w") as f:
        f.write(content)
