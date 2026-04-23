from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


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


class AIMaturitySignal(BaseModel):
    signal: str
    weight: str  # "high" | "medium" | "low"
    present: bool
    evidence: Optional[str] = None


class HiringSignalBrief(BaseModel):
    company_name: str
    crunchbase_id: str
    funding_event: Optional[FundingEvent] = None
    open_role_count: int = 0
    job_post_velocity_60d: Optional[int] = None  # delta in open roles over 60 days
    weak_signal: bool = False  # True when open_role_count < 5
    layoff_event: Optional[LayoffEvent] = None
    leadership_change: Optional[LeadershipChange] = None
    ai_maturity_score: int = Field(0, ge=0, le=3)
    ai_maturity_confidence: str = "low"  # "low" | "medium" | "high"
    ai_maturity_signals: list[AIMaturitySignal] = []
    per_signal_confidence: dict[str, float] = {}
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class GapPractice(BaseModel):
    practice: str
    evidence_source: str
    peers_showing: int
    prospect_shows: bool = False


class PeerScore(BaseModel):
    company_name: str
    crunchbase_id: str
    ai_maturity_score: int
    industry: Optional[str] = None


class CompetitorGapBrief(BaseModel):
    company_name: str
    crunchbase_id: str
    sector: Optional[str] = None
    prospect_ai_maturity: int = 0
    prospect_percentile: Optional[float] = None  # 0–100
    top_quartile_peers: list[PeerScore] = []
    gap_practices: list[GapPractice] = []
    generated_at: datetime = Field(default_factory=datetime.utcnow)
