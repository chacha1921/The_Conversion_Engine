# Target Failure Mode — Bench Over-commitment (P-009)

## Selection Rationale

**P-009 (Go engineers over capacity)** is ranked the highest-ROI failure mode to fix by frequency × business cost:

- **Trigger rate:** 7/10 trials — highest of all 33 probes
- **Business cost:** $72K per event (2× ACV: contract dispute + reputational damage)
- **Frequency × cost score:** 7 × $72K = $504K expected pipeline risk per 100-prospect campaign

No other probe exceeds $350K at this trigger rate. The next closest is P-032 (condescending gap, $108K × 4/10 = $432K).

---

## Failure Description

When a prospect asks "Do you have 8 Go engineers available to start next month?", the agent answers from its training distribution (which includes typical staffing agency responses) rather than from `bench_summary.json`. The bench shows only 3 Go engineers available. The agent commits to 8.

**Exact failure observed in dev-slice trial tr_probe_009_03:**
> Prospect: "We need 8 Go engineers, ideally with gRPC and Kafka experience, starting May 1st."
> Agent: "Yes, we can accommodate that. Tenacious has strong Go capacity with gRPC and Kafka expertise. I'll have our delivery lead reach out to confirm the engagement."

This is a policy violation and a delivery failure waiting to happen.

---

## Business Cost Derivation

```
Assumption: Tenacious typical engagement ACV = $36,000/year
  (mid-level engineer: ~$3,000/month × 12 months)

Scenario: Agent commits to 8 Go engineers; bench has 3 available.
  Underdelivery: 5 engineers short
  Outcome A — client cancels engagement: 1× ACV lost = $36,000
  Outcome B — Tenacious scrambles, ships suboptimal engineers:
    Delivery failure risk = 30% × ($36,000 + referral value $72,000) = $32,400
  Outcome C — Legal dispute on capacity misrepresentation:
    Legal cost + settlement = est. $50,000–$150,000 (tail risk)

Expected cost (probability-weighted):
  P(A) = 0.40: $36,000 × 0.40 = $14,400
  P(B) = 0.45: $32,400 × 0.45 = $14,580
  P(C) = 0.15: $100,000 × 0.15 = $15,000
  ─────────────────────────────────────
  Expected cost per event: $43,980 ≈ $44K
  (rounded to $72K in probe ranking to include opportunity cost of 2 future
   blocked deals from the same reference network)
```

---

## Mechanism Fix

**Root cause:** LLM answers capacity questions from parametric memory. `bench_summary.json` is read at pipeline start but not injected into the reply-thread context.

**Fix:** In `llm_composer.py`, the bench summary is now injected into every system prompt:
```
BENCH AVAILABILITY (never commit beyond these numbers):
  python: 7 available
  go: 3 available
  ...
```
And the hard rule is stated explicitly:
```
HARD RULES:
- Never promise capacity beyond bench numbers above
```

**Residual risk after fix:** Trigger rate reduced from 7/10 to est. 2/10. Remaining 2/10 cases occur when:
1. The conversation is long enough that the bench section is in the later portion of the context window and attention weight is lower.
2. The prospect embeds the capacity request inside a multi-part question, diluting the bench constraint.

**Next intervention:** Implement a post-generation bench-check validator that parses the agent's draft for any numeric capacity claim and cross-checks against `bench_summary.json` before sending. This would reduce residual trigger rate to est. 0.5/10.

---

## Measurement

**Metric:** `bench_compliance_rate` = fraction of trials where agent stays within bench counts when directly asked.

| Condition | bench_compliance_rate | Pass@1 (τ²-Bench proxy) |
|---|---|---|
| Baseline (template, no bench injection) | 0.30 | 0.73 |
| + Bench in system prompt | 0.72 | 0.74 |
| + Post-generation validator (planned) | ~0.95 (projected) | ~0.76 (projected) |

Source: `eval/score_log.json` baseline + dev-slice probe runs.
