from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Shared sub-models ──────────────────────────────────────────────────────

class EnrichmentBrief(BaseModel):
    crunchbase_id: str
    company_name: str
    industry: Optional[str] = None
    size: Optional[str] = None
    location: Optional[str] = None
    funding_total_usd: Optional[float] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    homepage_url: Optional[str] = None
    last_enriched_at: datetime = Field(default_factory=datetime.utcnow)


class FundingEvent(BaseModel):
    announced_on: Optional[str] = None
    amount_usd: Optional[float] = None
    series: Optional[str] = None
    days_ago: Optional[int] = None


class LayoffEvent(BaseModel):
    date: Optional[str] = None
    headcount_lost: Optional[int] = None
    pct_cut: Optional[float] = None
    source: Optional[str] = None
    days_ago: Optional[int] = None


class LeadershipChange(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    date: Optional[str] = None
    days_ago: Optional[int] = None


# Signal enum values must match schemas/hiring_signal_brief.schema.json exactly
SignalName = Literal[
    "ai_adjacent_open_roles",
    "named_ai_ml_leadership",
    "github_org_activity",
    "executive_commentary",
    "modern_data_ml_stack",
    "strategic_communications",
]


class AIMaturitySignal(BaseModel):
    signal: SignalName
    weight: Literal["high", "medium", "low"]
    present: bool
    confidence: Literal["high", "medium", "low"] = "low"
    evidence: Optional[str] = None
    source_url: Optional[str] = None


# ── HiringSignalBrief sub-models ───────────────────────────────────────────

class HiringVelocity(BaseModel):
    open_roles_today: int = 0
    open_roles_60_days_ago: int = 0
    velocity_label: Literal[
        "tripled_or_more", "doubled", "increased_modestly",
        "flat", "declined", "insufficient_signal"
    ] = "insufficient_signal"
    signal_confidence: float = Field(0.0, ge=0.0, le=1.0)
    sources: list[str] = []


class BenchToBriefMatch(BaseModel):
    required_stacks: list[str] = []
    bench_available: bool = False
    gaps: list[str] = []


class DataSourceCheck(BaseModel):
    source: str
    status: Literal["success", "partial", "no_data", "error", "rate_limited"]
    error_message: Optional[str] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


HonestyFlag = Literal[
    "weak_hiring_velocity_signal",
    "weak_ai_maturity_signal",
    "conflicting_segment_signals",
    "layoff_overrides_funding",
    "bench_gap_detected",
    "tech_stack_inferred_not_confirmed",
]

SegmentMatch = Literal[
    "segment_1_series_a_b",
    "segment_2_mid_market_restructure",
    "segment_3_leadership_transition",
    "segment_4_specialized_capability",
    "abstain",
]


# ── HiringSignalBrief ──────────────────────────────────────────────────────

class HiringSignalBrief(BaseModel):
    # Required by schema
    prospect_domain: str = ""
    prospect_name: str = ""
    primary_segment_match: SegmentMatch = "abstain"
    segment_confidence: float = Field(0.0, ge=0.0, le=1.0)
    data_sources_checked: list[DataSourceCheck] = []
    honesty_flags: list[HonestyFlag] = []

    # Legacy fields kept for internal pipeline use
    company_name: str
    crunchbase_id: str
    funding_event: Optional[FundingEvent] = None
    hiring_velocity: HiringVelocity = Field(default_factory=HiringVelocity)
    open_role_count: int = 0
    job_post_velocity_60d: Optional[int] = None
    weak_signal: bool = False
    layoff_event: Optional[LayoffEvent] = None
    leadership_change: Optional[LeadershipChange] = None
    ai_maturity_score: int = Field(0, ge=0, le=3)
    ai_maturity_confidence: str = "low"
    ai_maturity_signals: list[AIMaturitySignal] = []
    per_signal_confidence: dict[str, float] = {}
    bench_to_brief_match: BenchToBriefMatch = Field(default_factory=BenchToBriefMatch)
    tech_stack: list[str] = []
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ── CompetitorGapBrief sub-models ──────────────────────────────────────────

class PeerEvidence(BaseModel):
    competitor_name: str
    evidence: str
    source_url: str


class GapPractice(BaseModel):
    practice: str
    prospect_state: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"
    peer_evidence: list[PeerEvidence] = []
    segment_relevance: list[SegmentMatch] = []
    # Legacy fields
    evidence_source: str = ""
    peers_showing: int = 0
    prospect_shows: bool = False


class PeerScore(BaseModel):
    company_name: str
    crunchbase_id: str
    domain: str = ""
    ai_maturity_score: int
    ai_maturity_justification: list[str] = []
    headcount_band: Literal[
        "15_to_80", "80_to_200", "200_to_500", "500_to_2000", "2000_plus"
    ] = "80_to_200"
    top_quartile: bool = False
    sources_checked: list[str] = []
    industry: Optional[str] = None


class GapQualitySelfCheck(BaseModel):
    all_peer_evidence_has_source_url: bool = False
    at_least_one_gap_high_confidence: bool = False
    prospect_silent_but_sophisticated_risk: bool = False


# ── CompetitorGapBrief ─────────────────────────────────────────────────────

class CompetitorGapBrief(BaseModel):
    company_name: str
    crunchbase_id: str
    prospect_domain: str = ""
    prospect_sector: str = ""
    prospect_sub_niche: Optional[str] = None
    sector: Optional[str] = None          # legacy alias for prospect_sector
    prospect_ai_maturity: int = 0
    prospect_ai_maturity_score: int = 0   # schema alias
    prospect_percentile: Optional[float] = None
    sector_top_quartile_benchmark: float = 0.0
    competitors_analyzed: list[PeerScore] = []
    top_quartile_peers: list[PeerScore] = []  # legacy alias
    gap_practices: list[GapPractice] = []
    gap_findings: list[GapPractice] = []      # schema alias
    suggested_pitch_shift: str = ""
    gap_quality_self_check: GapQualitySelfCheck = Field(
        default_factory=GapQualitySelfCheck
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
