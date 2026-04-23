"""
ICP Classifier — assigns a prospect to one of four Tenacious segments.
Segment names are fixed for grading; do not rename.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .enrichment.models import HiringSignalBrief


class Segment(str, Enum):
    FUNDED_STARTUP = "recently_funded_series_a_b"
    RESTRUCTURING = "mid_market_restructuring"
    LEADERSHIP_TRANSITION = "engineering_leadership_transition"
    CAPABILITY_GAP = "specialized_capability_gap"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    segment: Segment
    confidence: float          # 0.0 – 1.0
    primary_signal: str
    pitch_language: str
    abstain: bool = False      # True when confidence < threshold

    @property
    def segment_label(self) -> str:
        return self.segment.value


_CONFIDENCE_THRESHOLD = 0.40
_FUNDING_WINDOW_DAYS = 180
_LAYOFF_WINDOW_DAYS = 120
_LEADERSHIP_WINDOW_DAYS = 90
_CAPABILITY_MIN_AI_MATURITY = 2


def classify(brief: HiringSignalBrief) -> ClassificationResult:
    scores: list[tuple[Segment, float, str, str]] = []

    # ── Segment 1: Recently funded Series A/B ─────────────────────────
    if brief.funding_event:
        days = brief.funding_event.days_ago or 999
        series = (brief.funding_event.series or "").lower()
        is_series_ab = any(s in series for s in ["series a", "series b", "seed"])
        if days <= _FUNDING_WINDOW_DAYS and is_series_ab:
            conf = 1.0 - (days / _FUNDING_WINDOW_DAYS) * 0.4
            pitch = (
                "Scale your AI team faster than in-house hiring can support"
                if brief.ai_maturity_score >= 2
                else "Stand up your first AI function with a dedicated squad"
            )
            scores.append((Segment.FUNDED_STARTUP, round(conf, 2), f"Series A/B {days}d ago", pitch))

    # ── Segment 2: Mid-market restructuring ───────────────────────────
    if brief.layoff_event:
        days = brief.layoff_event.days_ago or 999
        if days <= _LAYOFF_WINDOW_DAYS:
            conf = 0.75 - (days / _LAYOFF_WINDOW_DAYS) * 0.25
            scores.append((
                Segment.RESTRUCTURING,
                round(conf, 2),
                f"Layoff {days}d ago ({brief.layoff_event.pct_cut or '?'}% cut)",
                "Replace higher-cost roles with offshore equivalents while keeping delivery capacity",
            ))

    # ── Segment 3: Leadership transition ──────────────────────────────
    if brief.leadership_change:
        days = brief.leadership_change.days_ago or 999
        if days <= _LEADERSHIP_WINDOW_DAYS:
            conf = 0.80 - (days / _LEADERSHIP_WINDOW_DAYS) * 0.30
            scores.append((
                Segment.LEADERSHIP_TRANSITION,
                round(conf, 2),
                f"New {brief.leadership_change.role or 'tech leader'} {days}d ago",
                "New leaders routinely reassess vendor mix in their first 6 months — this is a narrow high-conversion window",
            ))

    # ── Segment 4: Specialized capability gap ─────────────────────────
    if brief.ai_maturity_score >= _CAPABILITY_MIN_AI_MATURITY:
        conf = 0.55 + (brief.ai_maturity_score - 2) * 0.15
        if brief.ai_maturity_confidence == "high":
            conf = min(conf + 0.10, 1.0)
        scores.append((
            Segment.CAPABILITY_GAP,
            round(conf, 2),
            f"AI maturity score {brief.ai_maturity_score}/3 ({brief.ai_maturity_confidence} confidence)",
            "Project-based consulting for a specific AI build where in-house skills don't match the need",
        ))

    if not scores:
        return ClassificationResult(
            segment=Segment.UNKNOWN,
            confidence=0.0,
            primary_signal="No qualifying signal found",
            pitch_language="Generic exploratory email only — do not use a segment-specific pitch",
            abstain=True,
        )

    # Pick highest-confidence segment
    best = max(scores, key=lambda x: x[1])
    segment, conf, signal, pitch = best

    abstain = conf < _CONFIDENCE_THRESHOLD
    if abstain:
        pitch = "Generic exploratory email only — confidence below threshold for segment-specific pitch"

    return ClassificationResult(
        segment=segment,
        confidence=conf,
        primary_signal=signal,
        pitch_language=pitch,
        abstain=abstain,
    )
