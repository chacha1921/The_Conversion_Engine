"""
AI maturity scorer (0–3) based on public signals.
All signals are derived from data already collected by other enrichment modules
or passed in as text extracted from job posts / web scraping.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from .models import AIMaturitySignal

# Weight mapping: high=3, medium=2, low=1
_WEIGHTS = {"high": 3, "medium": 2, "low": 1}

# Thresholds to map weighted sum → 0-3 score
# Max possible weighted sum = (3+3+2+2+1+1) = 12
_THRESHOLDS = [
    (9, 3),   # strong signal → score 3
    (5, 2),   # moderate → score 2
    (2, 1),   # weak → score 1
    (0, 0),   # none → score 0
]

AI_ROLE_KEYWORDS = [
    "machine learning", "ml engineer", "applied scientist", "llm engineer",
    "ai engineer", "data scientist", "nlp engineer", "ai product manager",
    "research scientist", "deep learning", "reinforcement learning",
]

ML_STACK_TOOLS = [
    "dbt", "snowflake", "databricks", "weights & biases", "wandb",
    "ray", "vllm", "mlflow", "kubeflow", "sagemaker", "vertex ai",
]

AI_LEADERSHIP_TITLES = [
    "head of ai", "vp of data", "chief scientist", "chief ai officer",
    "director of ml", "director of ai", "vp of machine learning",
    "head of machine learning", "chief data scientist",
]


@dataclass
class RawSignals:
    job_titles: list[str]                  # all open role titles (lowercase)
    total_open_roles: int
    leadership_titles: list[str]           # team page titles (lowercase)
    github_ai_repos: int                   # count of AI-adjacent public repos
    exec_ai_commentary: bool               # CEO/CTO mentioned AI in last 12 months
    ml_stack_tools: list[str]              # detected tools (lowercase)
    ai_in_strategic_comms: bool            # annual report / fundraising doc


def score(signals: RawSignals) -> tuple[int, str, list[AIMaturitySignal]]:
    """
    Returns (score 0-3, confidence 'low'|'medium'|'high', signal list).
    """
    evidence: list[AIMaturitySignal] = []
    weighted_sum = 0.0
    signal_count = 0

    # ── High weight signals ────────────────────────────────────────────
    ai_role_count = sum(
        1 for t in signals.job_titles
        if any(kw in t.lower() for kw in AI_ROLE_KEYWORDS)
    )
    ai_role_fraction = ai_role_count / max(signals.total_open_roles, 1)
    ai_roles_present = ai_role_fraction >= 0.10 or ai_role_count >= 2

    evidence.append(AIMaturitySignal(
        signal="AI-adjacent open roles",
        weight="high",
        present=ai_roles_present,
        evidence=f"{ai_role_count} AI roles of {signals.total_open_roles} total ({ai_role_fraction:.0%})",
    ))
    if ai_roles_present:
        weighted_sum += _WEIGHTS["high"]
        signal_count += 1

    leadership_ai = any(
        any(t in title for t in AI_LEADERSHIP_TITLES)
        for title in signals.leadership_titles
    )
    evidence.append(AIMaturitySignal(
        signal="Named AI/ML leadership",
        weight="high",
        present=leadership_ai,
        evidence=", ".join(signals.leadership_titles[:3]) if signals.leadership_titles else "none found",
    ))
    if leadership_ai:
        weighted_sum += _WEIGHTS["high"]
        signal_count += 1

    # ── Medium weight signals ──────────────────────────────────────────
    github_active = signals.github_ai_repos >= 2
    evidence.append(AIMaturitySignal(
        signal="Public GitHub AI/ML repo activity",
        weight="medium",
        present=github_active,
        evidence=f"{signals.github_ai_repos} AI-adjacent repos found",
    ))
    if github_active:
        weighted_sum += _WEIGHTS["medium"]
        signal_count += 1

    evidence.append(AIMaturitySignal(
        signal="Exec AI commentary (last 12 months)",
        weight="medium",
        present=signals.exec_ai_commentary,
        evidence="CEO/CTO mentioned AI as strategic priority" if signals.exec_ai_commentary else "no public commentary found",
    ))
    if signals.exec_ai_commentary:
        weighted_sum += _WEIGHTS["medium"]
        signal_count += 1

    # ── Low weight signals ─────────────────────────────────────────────
    ml_stack_found = [t for t in signals.ml_stack_tools if t in ML_STACK_TOOLS]
    ml_stack_present = len(ml_stack_found) >= 1
    evidence.append(AIMaturitySignal(
        signal="Modern ML stack detected",
        weight="low",
        present=ml_stack_present,
        evidence=", ".join(ml_stack_found) if ml_stack_found else "none detected",
    ))
    if ml_stack_present:
        weighted_sum += _WEIGHTS["low"]
        signal_count += 1

    evidence.append(AIMaturitySignal(
        signal="AI in strategic comms",
        weight="low",
        present=signals.ai_in_strategic_comms,
        evidence="AI named in fundraising/annual report" if signals.ai_in_strategic_comms else "not found",
    ))
    if signals.ai_in_strategic_comms:
        weighted_sum += _WEIGHTS["low"]
        signal_count += 1

    # ── Map to 0–3 score ──────────────────────────────────────────────
    score_val = 0
    for threshold, s in _THRESHOLDS:
        if weighted_sum >= threshold:
            score_val = s
            break

    # ── Confidence ────────────────────────────────────────────────────
    high_signals_present = sum(
        1 for e in evidence if e.weight == "high" and e.present
    )
    if high_signals_present >= 2:
        confidence = "high"
    elif high_signals_present == 1 or signal_count >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    return score_val, confidence, evidence
