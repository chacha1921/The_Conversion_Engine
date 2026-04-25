# Failure Taxonomy — Tenacious Conversion Engine

Probes grouped by category, ranked by frequency × business cost. Trigger rates are from the initial dev-slice evaluation (10 trials per probe).

---

## Summary Table

| Category | Probes | Avg Trigger Rate | Max Business Cost | Category Rank |
|---|---|---|---|---|
| Bench Over-commitment | P-009–P-012 | 4.75/10 | $72K | 1 — Critical |
| Signal Over-claiming | P-005–P-008 | 3.75/10 | $72K (fabrication) | 1 — Critical |
| ICP Misclassification | P-001–P-004 | 3.5/10 | $72K | 2 — High |
| Tone Drift | P-013–P-015 | 4.0/10 | $10.8K/10 leads | 2 — High |
| Gap Over-claiming | P-031–P-033 | 3.0/10 | $108K | 2 — High |
| Dual-control Coordination | P-022–P-024 | 2.3/10 | deal loss | 3 — Medium |
| Scheduling Edge Cases | P-025–P-027 | 2.7/10 | $36K | 3 — Medium |
| Multi-thread Leakage | P-016–P-018 | 1.7/10 | $108K | 3 — Medium |
| Signal Reliability | P-028–P-030 | 2.0/10 | Legal risk | 3 — Medium |
| Cost Pathology | P-019–P-021 | 2.0/10 | $50/100 prospects | 4 — Low |

---

## Category Detail

### 1. Bench Over-commitment
**Core failure:** Agent commits to engineer capacity that does not exist in `bench_summary.json`.
**Root cause:** LLM answers capacity questions from training data rather than checking the bench file.
**Fix implemented:** Bench capacity text injected into every LLM system prompt. Honesty constraint enforced: if prospect asks for N engineers and bench shows M < N, agent must state M and route remainder to human.
**Remaining risk:** Bench file updated weekly; stale bench data between Monday refreshes could cause a one-day window of incorrect counts.

| Probe | Trigger Rate | Fixed? |
|---|---|---|
| P-009 Go over capacity | 7/10 | Partially — prompt injection reduces to 2/10 |
| P-010 NestJS committed | 5/10 | Yes — note in prompt |
| P-011 Healthcare lag | 3/10 | Yes — regulated-industry caveat in prompt |
| P-012 Rust not on bench | 4/10 | Yes — "not in bench" check added |

---

### 2. Signal Over-claiming
**Core failure:** Agent uses signals beyond what the data supports (stale, weak, or fabricated).
**Root cause:** Template emails hard-coded "scaling rapidly" language without checking `weak_signal` flag or `open_role_count`.
**Fix implemented:** All email composition now goes through `llm_composer.py` which injects `open_role_count` and `weak_signal` directly into the hard-rules section of the system prompt.
**Remaining risk:** LLM may still hallucinate signal language if the system prompt is very long and the constraint is buried.

| Probe | Trigger Rate | Fixed? |
|---|---|---|
| P-005 Sub-5-role language | 6/10 | Partially — 2/10 after prompt fix |
| P-006 Zero roles assertion | 3/10 | Yes |
| P-007 Stale funding | 2/10 | Yes — 180-day window enforced in classifier |
| P-008 Low maturity framed high | 4/10 | Partially — hedging language added |

---

### 3. ICP Misclassification
**Core failure:** Wrong segment selected due to overlapping signals or window boundary conditions.
**Root cause:** Classifier picks the highest-confidence segment without flagging conflicting signals in the honesty_flags field.
**Fix implemented:** `honesty_flags` field in `HiringSignalBrief` now includes `layoff_overrides_funding` when both signals present. Classifier logic adjusted to weight restructuring over funding when layoff is within 120 days.
**Remaining risk:** Simultaneous leadership change + layoff still produces ambiguous output; segment 3 may win over segment 2 incorrectly.

| Probe | Trigger Rate | Fixed? |
|---|---|---|
| P-001 Funded + Layoff | 4/10 | Partially — honesty flag added, pitch not fully corrected |
| P-002 Funding outside window | 3/10 | Yes |
| P-003 AI brand name zero maturity | 2/10 | Yes — hard gate enforced |
| P-004 Layoff + new CTO | 5/10 | Partially |

---

### 4. Tone Drift
**Core failure:** Agent language drifts from the five Tenacious tone markers after multiple turns.
**Root cause:** Conversation history grows; style guide context is diluted in longer prompts.
**Fix implemented:** `tone_guard.enforce()` called on every outbound draft. `style_guide.md` re-injected on every LLM call via `llm_composer.py`.
**Remaining risk:** Tone guard itself uses an LLM call; if the tone-guard model has a different calibration, it may pass drifted drafts.

| Probe | Trigger Rate | Fixed? |
|---|---|---|
| P-013 Direct marker lost | 5/10 | Partially — tone_guard catches 3/5 |
| P-014 Apologetic on pushback | 4/10 | Partially |
| P-015 Subject line filler | 3/10 | Yes — subject constraint in system prompt |

---

### 5. Gap Over-claiming
**Core failure:** Competitor gap framed as assertion rather than research question, or pitched to wrong audience.
**Root cause:** `gap_findings` injected into email context without confidence check; agent treats all gaps as high-confidence.
**Fix implemented:** Discovery brief Section 3 splits high/low confidence gaps and explicitly labels low-confidence gaps as "do not assert." `suggested_pitch_shift` field drives framing in LLM prompt.
**Remaining risk:** If `gap_findings` list is empty, agent may fabricate a gap from general B2B knowledge.

| Probe | Trigger Rate | Fixed? |
|---|---|---|
| P-031 Gap without peer evidence | 3/10 | Partially |
| P-032 Condescending framing | 4/10 | Partially — tone_guard catches most |
| P-033 Gap to top-quartile | 2/10 | Yes — suggested_pitch_shift overrides |

---

### 6–10. Lower-priority Categories

**Dual-control Coordination (P-022–P-024):** Booking flow gated on explicit `prospect_email` check. `handle_booking_webhook()` does not auto-rebook cancelled events. Residual risk: agent interprets vague "book me in" as consent.

**Scheduling Edge Cases (P-025–P-027):** `book_slot()` passes `timezone_str` to Cal.com. Residual risk: pytz not installed in Docker container; DST edge case for Europe/London not tested in CI.

**Multi-thread Leakage (P-016–P-018):** `thread_store` keys on `(company_id, contact_id)` tuple. `company_id = crunchbase_id` (not fuzzy name match). Residual risk: if crunchbase_id is missing, fallback to company_name match could cause leakage.

**Signal Reliability (P-028–P-030):** `ai_maturity_score` computed from structured signals only, not company name. Layoff signal always hedged as "based on public reports." Residual risk: layoffs.fyi has false positives in ~5% of entries.

**Cost Pathology (P-019–P-021):** `max_retries=2` in `tone_guard.enforce()`. OpenRouter calls have `max_tokens=450` cap. Residual risk: long conversation histories not yet summarised/truncated.
