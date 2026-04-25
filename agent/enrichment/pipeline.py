"""
Full enrichment pipeline.
Runs all enrichment steps and produces the three brief JSON artifacts.
All output fields match schemas/hiring_signal_brief.schema.json and
schemas/competitor_gap_brief.schema.json exactly.
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from .crunchbase import lookup as crunchbase_lookup
from .layoffs import check as layoffs_check
from .leadership import check_sync as leadership_check
from .ai_maturity import RawSignals, score as ai_score
from .job_posts import fetch_job_titles_sync, velocity_label
from .models import (
    DataSourceCheck,
    EnrichmentBrief,
    GapPractice,
    GapQualitySelfCheck,
    HiringSignalBrief,
    HiringVelocity,
    CompetitorGapBrief,
    FundingEvent,
    PeerEvidence,
    PeerScore,
    BenchToBriefMatch,
)

logger = logging.getLogger(__name__)


def _domain_from_url(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc or ""
    except Exception:
        return ""


def _headcount_band(size_str: Optional[str]) -> str:
    """Map Crunchbase size string to schema headcount_band enum."""
    if not size_str:
        return "80_to_200"
    s = size_str.lower().replace(",", "").replace(" ", "")
    try:
        low = int(s.split("-")[0])
    except (ValueError, IndexError):
        return "80_to_200"
    if low < 80:
        return "15_to_80"
    if low < 200:
        return "80_to_200"
    if low < 500:
        return "200_to_500"
    if low < 2000:
        return "500_to_2000"
    return "2000_plus"


def _load_cached_briefs(output_dir: str) -> Optional[tuple[EnrichmentBrief, HiringSignalBrief, CompetitorGapBrief]]:
    """Return pre-seeded briefs if all three JSON files exist with valid signals."""
    enrich_path = os.path.join(output_dir, "enrichment_brief.json")
    hiring_path = os.path.join(output_dir, "hiring_signal_brief.json")
    gap_path = os.path.join(output_dir, "competitor_gap_brief.json")
    if not (os.path.exists(enrich_path) and os.path.exists(hiring_path) and os.path.exists(gap_path)):
        return None
    try:
        with open(enrich_path) as f:
            eb = EnrichmentBrief.model_validate_json(f.read())
        with open(hiring_path) as f:
            data = json.load(f)
            # Only use cached brief if it has meaningful signal data
            psc = data.get("per_signal_confidence", {})
            if not any(v > 0 for v in psc.values()):
                return None
            hb = HiringSignalBrief.model_validate(data)
        with open(gap_path) as f:
            gb = CompetitorGapBrief.model_validate_json(f.read())
        logger.info("Using pre-seeded briefs from %s", output_dir)
        return eb, hb, gb
    except Exception as e:
        logger.warning("Could not load cached briefs from %s: %s", output_dir, e)
        return None


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

    # Fast-path: return pre-seeded briefs (used for demo companies)
    cached = _load_cached_briefs(output_dir)
    if cached:
        return cached
    sources: list[DataSourceCheck] = []
    now = datetime.now(timezone.utc)

    # ── Step 1: Crunchbase firmographics ──────────────────────────────
    brief = crunchbase_lookup(company_name)
    if brief is None:
        brief = EnrichmentBrief(
            crunchbase_id="not-found",
            company_name=company_name,
            last_enriched_at=now,
        )
        sources.append(DataSourceCheck(source="crunchbase_odm", status="no_data", fetched_at=now))
    else:
        sources.append(DataSourceCheck(source="crunchbase_odm", status="success", fetched_at=now))

    _write_json(brief.model_dump_json(indent=2), output_dir, "enrichment_brief.json")

    # ── Step 2: Layoff signal ─────────────────────────────────────────
    layoff = None
    try:
        layoff = layoffs_check(company_name)
        sources.append(DataSourceCheck(
            source="layoffs_fyi",
            status="success" if layoff else "no_data",
            fetched_at=now,
        ))
    except Exception as e:
        sources.append(DataSourceCheck(source="layoffs_fyi", status="error", error_message=str(e), fetched_at=now))

    # ── Step 3: Leadership change ─────────────────────────────────────
    leadership = None
    try:
        leadership = leadership_check(company_name, press_release_url)
        sources.append(DataSourceCheck(
            source="press_release_scrape" if press_release_url else "crunchbase_people",
            status="success" if leadership else "no_data",
            fetched_at=now,
        ))
    except Exception as e:
        sources.append(DataSourceCheck(source="leadership_check", status="error", error_message=str(e), fetched_at=now))

    # ── Step 4: Job posts ─────────────────────────────────────────────
    job_titles: list[str] = []
    if careers_url:
        try:
            job_titles = fetch_job_titles_sync(careers_url)
            sources.append(DataSourceCheck(
                source="company_careers_page",
                status="success" if job_titles else "no_data",
                fetched_at=now,
            ))
        except Exception as e:
            sources.append(DataSourceCheck(source="company_careers_page", status="error", error_message=str(e), fetched_at=now))

    open_role_count = len(job_titles)
    weak_signal = open_role_count < 5
    vel_label = velocity_label(open_role_count, None)  # no 60d snapshot yet
    hiring_vel = HiringVelocity(
        open_roles_today=open_role_count,
        open_roles_60_days_ago=0,
        velocity_label=vel_label,
        signal_confidence=0.5 if careers_url else 0.0,
        sources=["company_careers_page"] if careers_url else [],
    )

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

    # ── Honesty flags ─────────────────────────────────────────────────
    honesty_flags = []
    if weak_signal:
        honesty_flags.append("weak_hiring_velocity_signal")
    if ai_score_val <= 1 and ai_confidence == "low":
        honesty_flags.append("weak_ai_maturity_signal")
    if layoff and brief.funding_total_usd and brief.funding_total_usd > 0:
        honesty_flags.append("layoff_overrides_funding")

    prospect_domain = _domain_from_url(brief.homepage_url)

    hiring_brief = HiringSignalBrief(
        prospect_domain=prospect_domain,
        prospect_name=company_name,
        primary_segment_match="abstain",   # updated by classifier in main.py
        segment_confidence=0.0,            # updated by classifier in main.py
        data_sources_checked=sources,
        honesty_flags=honesty_flags,
        company_name=company_name,
        crunchbase_id=brief.crunchbase_id,
        funding_event=FundingEvent(
            series=None, amount_usd=None, days_ago=None
        ) if brief.funding_total_usd else None,
        hiring_velocity=hiring_vel,
        open_role_count=open_role_count,
        job_post_velocity_60d=None,
        weak_signal=weak_signal,
        layoff_event=layoff,
        leadership_change=leadership,
        ai_maturity_score=ai_score_val,
        ai_maturity_confidence=ai_confidence,
        ai_maturity_signals=ai_signals,
        per_signal_confidence={
            s.signal: ({"high": 1.0, "medium": 0.67, "low": 0.33}.get(s.weight, 0.33) if s.present else 0.0)
            for s in ai_signals
        },
        bench_to_brief_match=BenchToBriefMatch(
            required_stacks=[],
            bench_available=True,
            gaps=[],
        ),
        tech_stack=[],
    )
    _write_json(hiring_brief.model_dump_json(indent=2), output_dir, "hiring_signal_brief.json")

    # ── Step 6: Competitor gap brief ──────────────────────────────────
    competitor_brief = _build_gap_brief(company_name, brief, ai_score_val, prospect_domain)
    _write_json(competitor_brief.model_dump_json(indent=2), output_dir, "competitor_gap_brief.json")

    return brief, hiring_brief, competitor_brief


def _build_gap_brief(
    company_name: str,
    brief: EnrichmentBrief,
    prospect_score: int,
    prospect_domain: str = "",
) -> CompetitorGapBrief:
    from .crunchbase import sample as crunchbase_sample

    sector = brief.industry or ""

    try:
        peers_raw = crunchbase_sample(50)
    except FileNotFoundError:
        return CompetitorGapBrief(
            company_name=company_name,
            crunchbase_id=brief.crunchbase_id,
            prospect_domain=prospect_domain,
            prospect_sector=sector,
            sector=sector,
            prospect_ai_maturity=prospect_score,
            prospect_ai_maturity_score=prospect_score,
        )

    peer_scores: list[PeerScore] = []
    for peer in peers_raw:
        if peer.company_name == company_name:
            continue
        default_signals = RawSignals(
            job_titles=[], total_open_roles=0, leadership_titles=[],
            github_ai_repos=0, exec_ai_commentary=False,
            ml_stack_tools=[], ai_in_strategic_comms=False,
        )
        s, _, _ = ai_score(default_signals)
        peer_domain = _domain_from_url(peer.homepage_url)
        peer_scores.append(PeerScore(
            company_name=peer.company_name,
            crunchbase_id=peer.crunchbase_id,
            domain=peer_domain,
            ai_maturity_score=s,
            ai_maturity_justification=["Scored from Crunchbase ODM with default signal set"],
            headcount_band=_headcount_band(peer.size),
            top_quartile=False,  # updated below
            sources_checked=[f"https://crunchbase.com/organization/{peer.crunchbase_id}"],
            industry=peer.industry,
        ))

    if not peer_scores:
        return CompetitorGapBrief(
            company_name=company_name,
            crunchbase_id=brief.crunchbase_id,
            prospect_domain=prospect_domain,
            prospect_sector=sector,
            sector=sector,
            prospect_ai_maturity=prospect_score,
            prospect_ai_maturity_score=prospect_score,
        )

    # Percentile and top-quartile
    scores = [p.ai_maturity_score for p in peer_scores]
    above = sum(1 for s in scores if s > prospect_score)
    percentile = round((1 - above / len(scores)) * 100, 1)

    sorted_peers = sorted(peer_scores, key=lambda p: p.ai_maturity_score, reverse=True)
    tq_cutoff = max(1, len(sorted_peers) // 4)
    for i, p in enumerate(sorted_peers):
        p.top_quartile = i < tq_cutoff

    top_quartile = [p for p in sorted_peers if p.top_quartile][:10]
    tq_benchmark = round(
        sum(p.ai_maturity_score for p in top_quartile) / max(len(top_quartile), 1), 2
    )

    # Gap findings with peer evidence
    gap_findings: list[GapPractice] = []

    if prospect_score < 3:
        tq_with_leadership = [p for p in top_quartile if p.ai_maturity_score >= 2]
        gap_findings.append(GapPractice(
            practice="Named Head of AI or Chief Scientist on public team page",
            prospect_state=(
                f"{company_name} has no named AI/ML leadership role on its public team page."
                if prospect_score < 2
                else f"{company_name} shows some AI leadership signal but below top-quartile peers."
            ),
            confidence="high" if len(tq_with_leadership) >= 2 else "medium",
            peer_evidence=[
                PeerEvidence(
                    competitor_name=p.company_name,
                    evidence=f"AI maturity score {p.ai_maturity_score}/3 — AI leadership signal present.",
                    source_url=p.sources_checked[0] if p.sources_checked else "",
                )
                for p in tq_with_leadership[:3]
            ],
            segment_relevance=["segment_1_series_a_b", "segment_4_specialized_capability"],
            evidence_source="Crunchbase ODM peer sample",
            peers_showing=len(tq_with_leadership),
            prospect_shows=prospect_score >= 2,
        ))

    if prospect_score < 2:
        tq_with_roles = [p for p in top_quartile if p.ai_maturity_score >= 1]
        gap_findings.append(GapPractice(
            practice="Active AI-adjacent open roles (ML Eng, LLM Eng, Applied Scientist)",
            prospect_state=(
                f"{company_name} has fewer than 2 AI-adjacent open roles detected."
                if prospect_score < 1
                else f"{company_name} shows limited AI hiring velocity vs top-quartile peers."
            ),
            confidence="medium",
            peer_evidence=[
                PeerEvidence(
                    competitor_name=p.company_name,
                    evidence=f"AI maturity score {p.ai_maturity_score}/3 — active AI hiring signal.",
                    source_url=p.sources_checked[0] if p.sources_checked else "",
                )
                for p in tq_with_roles[:2]
            ],
            segment_relevance=["segment_4_specialized_capability"],
            evidence_source="Public job boards (Crunchbase ODM proxy)",
            peers_showing=len(tq_with_roles),
            prospect_shows=prospect_score >= 1,
        ))

    # Only include gaps where prospect doesn't already show the practice
    gap_findings = [g for g in gap_findings if not g.prospect_shows]

    gap_quality = GapQualitySelfCheck(
        all_peer_evidence_has_source_url=all(
            e.source_url for g in gap_findings for e in g.peer_evidence
        ),
        at_least_one_gap_high_confidence=any(g.confidence == "high" for g in gap_findings),
        prospect_silent_but_sophisticated_risk=bool(prospect_score == 0 and brief.funding_total_usd and brief.funding_total_usd > 10_000_000),
    )

    suggested_pitch = (
        f"Lead with the AI leadership gap (high confidence). "
        f"{company_name} sits at the {percentile:.0f}th percentile in its sector. "
        f"Frame as a research question, not an assertion."
    ) if gap_findings else (
        f"{company_name} is already in the top quartile — pitch Tenacious as a scale accelerant, not a gap-filler."
    )

    return CompetitorGapBrief(
        company_name=company_name,
        crunchbase_id=brief.crunchbase_id,
        prospect_domain=prospect_domain,
        prospect_sector=sector,
        sector=sector,
        prospect_ai_maturity=prospect_score,
        prospect_ai_maturity_score=prospect_score,
        prospect_percentile=percentile,
        sector_top_quartile_benchmark=tq_benchmark,
        competitors_analyzed=sorted_peers[:10],
        top_quartile_peers=top_quartile,
        gap_practices=gap_findings,
        gap_findings=gap_findings,
        suggested_pitch_shift=suggested_pitch,
        gap_quality_self_check=gap_quality,
    )


def _write_json(content: str, directory: str, filename: str) -> None:
    with open(os.path.join(directory, filename), "w") as f:
        f.write(content)
