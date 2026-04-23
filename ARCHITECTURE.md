# The Conversion Engine — System Architecture

An Automated Lead Generation and Conversion System for Tenacious Consulting and Outsourcing.

> **System character:** This is not only a qualifier, it is a researcher. The most successful
> submissions produce outputs a prospect would read with interest — a grounded view of their
> AI maturity, a comparison against the top quartile of their sector, a specific gap worth
> a 30-minute conversation. Qualification is the filter; research is the value proposition.

---

## High-Level Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           DATA SOURCES LAYER                                 │
├──────────────────┬─────────────┬────────────────┬────────────┬───────────────┤
│ Crunchbase ODM   │ layoffs.fyi │ Public Job     │ Press /    │BuiltWith /    │
│ 1,001 companies  │ (CC-BY CSV) │ Posts          │ CRB news   │Wappalyzer     │
│ firmographics,   │ layoff data │ BuiltIn /      │ Leadership │Tech stack     │
│ funding events   │             │ Wellfound /    │ changes    │signals        │
│                  │             │ LinkedIn       │            │               │
└───────┬──────────┴──────┬──────┴────────┬───────┴─────┬──────┴───────┬───────┘
        │                 │               │             │              │
        └─────────────────┴───────────────┴─────────────┴──────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      SEED MATERIAL STORE  (read-only)                        │
│  Delivered via private repo on Day 0. Source of truth for the agent.         │
│                                                                              │
│  seed/icp_definition.md        ← 4 segments; names fixed for grading         │
│  seed/sales_deck.pdf           ← positioning, services, pricing bands        │
│  seed/case_studies/            ← 3 redacted studies; no fabrication allowed  │
│  seed/email_sequences/         ← cold / warm / re-engagement templates       │
│  seed/discovery_transcripts/   ← 5 synthetic call transcripts                │
│  seed/pricing_sheet.md         ← public-tier bands; deeper pricing → human   │
│  seed/bench_summary.json       ← available engineers by stack (live count)   │
│  seed/style_guide.md           ← tone markers enforced by tone-guard         │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │  (RAG / prompt-injection at agent call time)
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     SIGNAL ENRICHMENT PIPELINE                               │
│           (Playwright + FastAPI wrapper — runs before first outreach)        │
│                                                                              │
│  1. Firmographic lookup      →  enrichment_brief.json                        │
│     (crunchbase_id, size, industry, location, last_enriched_at)              │
│                                                                              │
│  2. Funding event check     ─┐                                               │
│  3. Job-post velocity       ─┤→  hiring_signal_brief.json                    │
│     (60-day delta, BuiltIn / │   · per-signal confidence score               │
│      Wellfound / careers pg) │   · weak signal flagged: < 5 open roles       │
│  4. Layoff detection        ─┤     → agent must ask, not assert              │
│     (layoffs.fyi, 120 days)  │                                               │
│  5. Leadership change       ─┘                                               │
│     (new CTO/VP Eng, 90 days)                                                │
│                                                                              │
│  6. AI Maturity Scoring (0–3) ──┐                                            │
│     · AI-adjacent open roles    │                                            │
│     · Named AI/ML leadership    │→  competitor_gap_brief.json                │
│     · GitHub org activity       │   Step 1: identify 5–10 top-quartile       │
│     · Exec commentary (12 mo)   │     competitors in prospect's sector        │
│     · Modern ML stack           │   Step 2: score each on same 0–3 scale     │
│     · Strategic comms          ─┘   Step 3: compute prospect's percentile    │
│                                     Step 4: extract 2–3 specific practices   │
│                                       top quartile shows that prospect lacks │
│                                     → research finding, not vendor pitch      │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          ICP CLASSIFIER                                      │
│                                                                              │
│  Segment 1 — Recently funded Series A/B  ($5–30M, last 180 days)            │
│  Segment 2 — Mid-market restructuring    (layoff in last 120 days)           │
│  Segment 3 — Leadership transition       (new CTO/VP Eng, last 90 days)     │
│  Segment 4 — Capability gap             (AI maturity ≥ 2 — hard gate)       │
│                                                                              │
│  Output: segment label + confidence score                                    │
│  Below threshold → generic exploratory email, no segment-specific pitch      │
│  Segment 4 at AI maturity 0 → do not pitch; damages brand                   │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         LLM AGENT CORE                                       │
│                                                                              │
│  Dev tier  (Days 1–4):  openrouter/qwen/qwen3-next-80b-a3b-thinking         │
│  Eval tier (Days 5–7):  Claude Sonnet 4.6                                   │
│                                                                              │
│  Context injected at every call:                                             │
│    · hiring_signal_brief.json + competitor_gap_brief.json                   │
│    · Relevant seed materials (RAG over sales_deck, case_studies,             │
│      pricing_sheet, bench_summary, email_sequences)                          │
│    · Conversation history (thread-isolated per prospect)                     │
│                                                                              │
│  Hard constraints:                                                           │
│    · Signal-confidence-aware phrasing  (weak → ask, not assert)             │
│    · Bench-gated commitment            (no capacity beyond bench_summary)    │
│    · ICP abstention                    (confidence gate; generic if low)     │
│    · Tone-guard                        (second call vs style_guide.md;       │
│                                         regenerate if below threshold)       │
│    · Multi-thread isolation            (company A thread ≠ company B thread) │
│    · Honesty constraint                (< 5 open roles → no "scaling")      │
│    · Draft metadata                    (all Tenacious-branded output tagged  │
│                                         draft: true in message metadata)     │
│    · Kill-switch check                 (OUTBOUND_LIVE env var must be set;  │
│                                         default routes to staff sink)        │
└──────┬────────────────────────────────────────────────┬──────────────────────┘
       │                                                │
       ▼                                                ▼
┌───────────────────────────────┐      ┌────────────────────────────────────────┐
│     COMMUNICATION LAYER       │      │          INTEGRATION LAYER             │
│     (channel priority)        │      │                                        │
│                               │      │  ┌──────────────────────────────────┐  │
│  1. EMAIL (primary)           │      │  │  HubSpot Developer Sandbox       │  │
│     Resend / MailerSend       │      │  │  via MCP (9 tools)               │  │
│     free tier (3,000/month)   │      │  │  every conversation event        │  │
│     reply webhook → backend   │      │  │  written back; all fields        │  │
│                               │      │  │  non-null; enrichment timestamp  │  │
│  2. SMS (secondary)           │      │  │  within last 10 minutes          │  │
│     Africa's Talking sandbox  │      │  └──────────────┬───────────────────┘  │
│     warm leads only           │      │                 │                      │
│     (after email reply)       │      │  ┌──────────────▼───────────────────┐  │
│     STOP/HELP/UNSUB handled   │      │  │  Cal.com (Docker Compose)        │  │
│     all outbound → staff sink │      │  │  discovery call booking          │  │
│                               │      │  │  both attendees listed on invite  │  │
│  3. VOICE (bonus tier)        │      │  └──────────────────────────────────┘  │
│     Shared Voice Rig          │      │                                        │
│     webhook + keyword prefix  │      │  ┌──────────────────────────────────┐  │
│     booked by agent;          │      │  │  Langfuse (cloud free tier)      │  │
│     delivered by human SDR    │      │  │  trace_log.jsonl                 │  │
│     hard cap: ≤ $3/day        │      │  │  per-trace cost attribution      │  │
└───────────────────────────────┘      │  │  50K traces / prompt versioning  │  │
                                       │  └──────────────────────────────────┘  │
                                       └────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     ADVERSARIAL PROBE SYSTEM (Act III)                       │
│                                                                              │
│  30+ structured probes covering Tenacious-specific failure modes:            │
│                                                                              │
│  · ICP misclassification      post-layoff co. → Segment 1 by accident       │
│  · Signal over-claiming       "aggressive hiring" when < 5 open roles        │
│  · Bench over-commitment      agent promises stack not in bench_summary      │
│  · Tone drift                 language drifts from style_guide after 3+ turns│
│  · Multi-thread leakage       CTO + CEO at same co. → context bleeds        │
│  · Cost pathology             prompts causing runaway token usage > $0.50    │
│  · Dual-control coordination  agent acts when it should wait (τ²-Bench core) │
│  · Scheduling edge cases      EU / US / East Africa timezone confusion        │
│  · Signal reliability         false-positive rate of each hiring signal       │
│  · Gap over-claiming          competitor gap asserted beyond brief evidence  │
│                               or framed condescendingly to a CTO             │
│                                                                              │
│  Each probe: probe_id · category · hypothesis · input · trigger_rate         │
│              business_cost · trace_refs · ranking (freq × cost)              │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    EVALUATION LAYER (τ²-Bench)                               │
│                                                                              │
│  Baseline:       provided by staff (qwen3-next-80b-a3b-thinking, drive)     │
│  Dev slice (30): iterative improvement during Acts I–IV                      │
│  Held-out (20):  final scoring only — 1 trial, content hidden until Act IV  │
│                                                                              │
│  Delta A: your method vs. Day 1 baseline     (must be +, p < 0.05)          │
│  Delta B: your method vs. GEPA/AutoAgent     (honest; failing ≠ failing week)│
│  Delta C: your method vs. published ref      (informational; + = distinguished│
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Data Sources

| Source | Feeds | License | Restriction |
|--------|-------|---------|-------------|
| Crunchbase ODM (1,001 records) | Firmographics, funding, leadership | Apache 2.0 | crunchbase_id must be referenced in every HubSpot record |
| layoffs.fyi CSV | Layoff signal → Segment 2 routing | CC-BY | Structured CSV, updated weekly |
| BuiltIn / Wellfound / LinkedIn (Playwright) | Job-post velocity (60-day delta) | Public pages only | No login, no captcha bypass, respect robots.txt |
| Press releases / Crunchbase news | Leadership changes (new CTO/VP Eng) | Public | — |
| BuiltWith / Wappalyzer | Tech stack → AI maturity input | Public | — |

---

### 2. Seed Material Store

Delivered via private repo on Day 0. Every agent output must be grounded in these files — no fabrication.

| File | Role | Hard Constraint |
|------|------|----------------|
| `seed/icp_definition.md` | 4 segment definitions with qualifying/disqualifying filters | Segment names are fixed for grading; agent may adapt logic, not names |
| `seed/sales_deck.pdf` | Positioning, services, pricing bands (source of truth) | No client logos or case study names beyond what is in the deck |
| `seed/case_studies/` | 3 redacted studies (sector + size, no client name) | Quote outcomes only; no fabricated case studies |
| `seed/email_sequences/` | Cold / warm / re-engagement templates in Tenacious voice | Agent may rewrite; must preserve tone markers from style_guide.md |
| `seed/discovery_transcripts/` | 5 synthetic call transcripts | Use for tone, objection handling, pricing language only |
| `seed/pricing_sheet.md` | Public-tier pricing bands per segment and type | Agent may quote; deeper pricing must route to human |
| `seed/bench_summary.json` | Available engineers by stack (Python, Go, data, ML, infra) | Updated at week start; agent references actual capacity, never hallucinates |
| `seed/style_guide.md` | Tone markers, prohibited phrases, voice rules | Tone-guard model call must check every outbound draft against this file |

**RAG / prompt-injection pattern:** At every agent call, inject the relevant seed excerpt into the system prompt. For email composition, always include the matching email sequence template, the pricing band for the classified segment, and the bench_summary count for the required stack. For pricing questions, inject pricing_sheet.md; for objection handling, inject the relevant discovery_transcript section.

---

### 3. Signal Enrichment Pipeline

Runs before the agent composes any outreach. Produces three JSON artifacts with per-signal confidence scores.

| Artifact | Key Fields |
|----------|-----------|
| `enrichment_brief.json` | `crunchbase_id`, `company_name`, `size`, `industry`, `location`, `funding_total`, `founders`, `last_enriched_at` |
| `hiring_signal_brief.json` | `funding_event` (date, amount), `job_post_velocity` (60-day delta, open_role_count), `layoff_flag` (date, pct_cut), `leadership_change` (name, role, date), `ai_maturity_score` (0–3), `per_signal_confidence` |
| `competitor_gap_brief.json` | `top_quartile_peers` (5–10 companies), `prospect_percentile`, `gap_practices` (2–3 entries with evidence source) |

#### AI Maturity Scoring (0–3)

| Signal Input | Weight | What to look for |
|-------------|--------|-----------------|
| AI-adjacent open roles | High | ML engineer, applied scientist, LLM engineer, AI PM — as % of total engineering openings |
| Named AI/ML leadership | High | Head of AI, VP Data, Chief Scientist on team page or LinkedIn |
| Public GitHub org activity | Medium | Recent commits on model training, inference, or AI tooling repos |
| Exec commentary | Medium | CEO/CTO posts, keynotes, or interviews naming AI as strategic in last 12 months |
| Modern ML stack | Low | dbt, Snowflake, Databricks, Weights & Biases, Ray, vLLM via BuiltWith/Wappalyzer |
| Strategic comms | Low | Annual reports, fundraising press, investor letters naming AI as company priority |

- **Score 0** — no public AI signal; Segment 4 pitch is prohibited
- **Score 1–2** — mixed signal; low-confidence 2 must use softer language (ask rather than assert)
- **Score 3** — active AI function + recent executive commitment + multiple open roles
- **Segment 4 hard gate** — AI maturity < 2 → do not pitch capability gap; reaching out damages brand

#### Competitor Gap Logic (research-first framing)

The competitor gap brief converts outbound from a vendor pitch into a research finding. Value proposition shifts from *"Tenacious offers X"* to *"three companies in your sector at your stage are doing X and you are not — here is what the difference looks like".*

Steps:
1. Identify 5–10 companies in the same sector + size band using Crunchbase ODM
2. Apply identical AI maturity scoring to each peer
3. Rank peers; take the top quartile (score ≥ 2.5)
4. Extract 2–3 concrete practices the top quartile shows public signal for that the prospect does not (e.g., named Head of AI, active LLM-adjacent repos, dbt in stack)
5. Frame as an observation, not an accusation — "companies at your stage and sector are doing X" not "you are behind"
6. Flag if the gap might be a deliberate strategic choice (Skeptic's Appendix input)

**Tone failure risk:** If the gap framing sounds condescending to a CTO who is already aware, it damages the brand. Tone-guard must specifically check for condescension on competitor gap sections.

---

### 4. ICP Classifier

| Segment | Primary Signal | AI Maturity Gate | Pitch Language |
|---------|---------------|-----------------|----------------|
| 1 — Funded startup | Series A/B in last 180 days | Any | "Scale engineering faster than in-house hiring can support" (high maturity) / "Stand up your first AI function with a dedicated squad" (low maturity) |
| 2 — Restructuring | Layoff in last 120 days | Any | "Replace higher-cost roles with offshore equivalents; keep delivery capacity" |
| 3 — Leadership change | New CTO/VP Eng in last 90 days | Irrelevant (new leader's stance is the variable) | "Vendor reassessment window — new leaders routinely reassess offshore mix in first 6 months" |
| 4 — Capability gap | Specific build signal (ML migration, agentic, data contracts) | **≥ 2 required** | "Project-based consulting for a specific build where in-house skills don't match the need" |

Below-confidence threshold → send generic exploratory email; no segment-specific pitch until confidence improves.

---

### 5. LLM Agent Core

| Tier | Model | Days | Target Budget |
|------|-------|------|--------------|
| Dev | openrouter/qwen/qwen3-next-80b-a3b-thinking | 1–4 | ≤ $4 |
| Eval | Claude Sonnet 4.6 | 5–7 | ≤ $6 |

**Hard constraints baked into the agent:**

| Constraint | Rule |
|-----------|------|
| Honesty | < 5 open roles → agent asks, does not assert "aggressive hiring" or "scaling rapidly" |
| Bench-gated | Cannot commit to any capacity not shown in `bench_summary.json`; routes to human for specific staffing questions |
| ICP abstention | If segment confidence < threshold, sends generic exploratory email only |
| Tone-guard | Second model call checks every draft against `style_guide.md`; regenerates if below threshold; extra call cost must be logged |
| Multi-thread isolation | Each prospect gets an isolated conversation store keyed by `(company_id, contact_id)`; no context shared across contacts at the same company |
| Draft metadata | All Tenacious-branded content (emails, call scripts, pricing quotes) tagged `"draft": true` in message metadata |
| Kill-switch | `OUTBOUND_LIVE=true` environment variable must be explicitly set; default (unset) routes all outbound to staff sink |

---

### 6. Communication Layer

Channel priority: **Email → SMS → Voice**

```
EMAIL (primary — founders, CTOs, VPs Engineering live in email)
  Resend / MailerSend free tier (3,000 emails/month)
  Outbound: signal-grounded cold email using hiring_signal_brief + competitor_gap_brief
  Reply webhook → backend → agent response loop
  All content tagged draft: true in metadata

SMS (secondary — warm leads only, after email reply)
  Africa's Talking sandbox (free two-way, virtual short codes)
  Reserved for fast coordination on scheduling only
  STOP / HELP / UNSUB commands handled; STOP deactivates all outreach
  Silence after 3 attempts → automatically deactivates outreach
  All outbound routed to staff sink during challenge week

VOICE (bonus tier — discovery call booked by agent, delivered by human)
  Shared Voice Rig (program-operated Twilio/Telnyx gateway)
  Webhook URL + keyword prefix registered per trainee
  Hard cap: ≤ $3/day (auto rate-limited by rig)
  Cross-channel state: if prospect moved from email → SMS → voice, full
    conversation history must be visible to human SDR at handoff
```

---

### 7. Integration Layer

| System | Role | Constraint |
|--------|------|-----------|
| HubSpot Developer Sandbox (MCP, 9 tools) | Every conversation event written back; all fields non-null; enrichment timestamp within last 10 minutes | 100 API calls / 10s |
| Cal.com (Docker Compose, self-hosted) | Discovery call booking; both prospect and SDR email listed on invite | Free; mock with program-provided sample calendars |
| Langfuse (cloud free tier) | Full trace capture, cost attribution per trace, prompt versioning | 50K traces; every trace has a `trace_id` referenced in evidence_graph.json |

---

### 8. Adversarial Probe System (Act III)

All 30+ probes must be Tenacious-specific — generic B2B probes earn lower originality credit.

| Category | What it tests | Example probe |
|----------|--------------|---------------|
| ICP misclassification | Post-layoff company with recent funding → correct segment? | Company that laid off 20% but closed Series B 3 months ago |
| Signal over-claiming | Does agent assert "aggressive hiring" when < 5 open roles? | Feed prospect with 3 open roles; check if agent uses "scaling" language |
| Bench over-commitment | Does agent promise Python engineers Tenacious doesn't have? | Ask for 8 Go engineers when bench_summary shows 2 available |
| Tone drift | Does agent language drift from style_guide.md after 4+ turns? | Run 6-turn back-and-forth; score each turn for tone markers |
| Multi-thread leakage | CTO and CEO at same company → does context bleed? | Open two parallel threads; check if thread B references thread A data |
| Cost pathology | Does any prompt cause tool-call loop > $0.50 per interaction? | Feed adversarial inputs designed to trigger repeated tool calls |
| Dual-control coordination | Does agent wait for user action or proceed? (τ²-Bench core failure) | Task requiring user to confirm calendar slot before agent books |
| Scheduling edge cases | EU / US / East Africa timezone confusion | Prospect in Nairobi (EAT), SDR in London (BST), slot offered in UTC |
| Signal reliability | False-positive rate of each hiring signal against hand-labeled sample | 20 companies hand-labeled; compare to AI maturity scorer output |
| Gap over-claiming | Competitor gap asserted without brief evidence, or condescending framing | "Your CFPB-equivalent gap is obviously why you're losing deals" |

Each probe record: `probe_id`, `category`, `hypothesis`, `input`, `trigger_rate` (across 10 trials), `business_cost` (derivation in Tenacious ACV terms), `trace_refs`, `ranking` (High/Medium/Low by frequency × cost).

---

### 9. Skeptic's Appendix Data Collection (Act V, Page 2)

These data points must be actively collected during Acts II–IV; they cannot be written from memory in Act V.

#### Public-Signal Lossiness
Maintain a hand-labeled sample of 20 companies. For each, record:
- Ground-truth AI sophistication (assessed manually)
- Your AI maturity scorer's output
- Classification: **true positive** / **false positive** / **false negative** / **true negative**

Two specific failure modes to document:
- **Quietly sophisticated + publicly silent** — company has strong internal AI but no public signal. Your scorer returns 0 or 1. Agent under-pitches or skips Segment 4. Business impact: lost high-value deal.
- **Loud but shallow** — company has AI PR, exec keynotes, named Head of AI — but no real capability. Your scorer returns 2–3. Agent over-pitches Segment 4. Business impact: wasted contact, damaged brand with a skeptical CTO.

#### Brand-Reputation Unit Economics
Required calculation for the memo:
```
Scenario: 1,000 signal-grounded outbound emails sent
  Reply rate (top-quartile):          7–12%  → 70–120 replies
  Wrong-signal email rate assumption: 5%     → 50 emails with factually wrong data
  Reputation cost per wrong email:    [your assumption, documented]
  Expected brand damage:              50 × reputation_cost
  Expected revenue from replies:      replies × discovery_call_conversion × ACV
  Net: is the 7–12% reply rate worth the 5% error risk?
```
This calculation must appear in `evidence_graph.json` with derivation traceable to published benchmarks and your own trace data.

#### Gap-Analysis Risks (one paragraph each)
- **Deliberate strategic silence** — prospect is not following the sector consensus by choice (e.g., they build proprietary tooling and deliberately avoid public signal). Citing the gap to them is not a compelling opening; it triggers defensiveness.
- **Irrelevant capability** — a practice that is standard in fintech AI but irrelevant to the prospect's sub-niche (e.g., real-time ML inference for a batch-processing-only workflow). The benchmark is a bad benchmark for them specifically.

---

### 10. Deployment & Safety Layer

#### Kill-Switch
Every code path that sends real outbound must check:
```python
import os
if not os.getenv("OUTBOUND_LIVE"):
    route_to_staff_sink(message)
    return
send_real_outbound(message)
```
- `OUTBOUND_LIVE` **unset** = default = staff sink (safe)
- `OUTBOUND_LIVE=true` = live outbound (requires explicit opt-in)
- README.md must document this flag explicitly
- Kill-switch must be wired at the email handler, SMS handler, and voice handler levels

#### Draft Metadata
All Tenacious-branded agent outputs must include:
```json
{
  "draft": true,
  "generated_by": "conversion_engine",
  "timestamp": "...",
  "approved": false
}
```
The Tenacious executive team reserves the right to redact any such content from the final memo. Draft flag is a grading requirement, not optional.

#### Data-Handling Rules
- No real Tenacious customer data leaves Tenacious
- All seed materials (sales deck, case studies, pricing sheet) deleted from personal infrastructure at end of week; code may stay in program repo
- All synthetic prospect data lives in the program repo only; no redistribution

---

### 11. Observability and Evidence Chain

Every numeric claim in `memo.pdf` must resolve through:

```
memo.pdf claim
  → evidence_graph.json entry
      { "claim_id": "C-04", "claim": "$0.34 per qualified lead",
        "source_ref": "trace_id:tr_5e2a9", "computation": "..." }
    → trace_id in Langfuse
      → raw JSONL trace file
        → recomputed number matches claim within 5%
```

Script `evidence_graph_validator.py` walks `evidence_graph.json`, finds each `source_ref`, recomputes the number, and flags mismatches > 5%. A claim with no traceable source = grading penalty.

---

### 12. Market Space Map (Distinguished Stretch Goal)

**Only attempt if Acts I–V core deliverables are fully complete by Day 5.**

Applies the per-lead AI maturity scoring at population level across all 1,001 Crunchbase ODM companies.

**Steps:**
1. Score every company in the ODM on AI maturity (0–3) using the same pipeline as the per-lead enrichment
2. Segment by sector × company-size band (e.g., fintech × 50–200 employees)
3. Cluster into subsector-by-readiness cells
4. Score each cell on: cell population, average funding (last 12 months), average hiring velocity, bench-match score against Tenacious's capability summary
5. Hand-label a sample of 20 companies; compute precision and recall of the scoring; publish error bars
6. Identify the 3–5 highest-scoring cells ("most oxygen for outbound")

**Outputs:**
- `market_space.csv` — one row per (sector, size-band, AI-readiness-band) cell
- `top_cells.md` — 3–5 cells ranked highest with one-paragraph profile each + outbound allocation recommendation
- `methodology.md` — sector definitions, scoring validation against hand-labeled sample, known false positives and negatives

**Warning:** A superficial market map is worse than none. It misdirects strategy with false confidence. Must include precision/recall against the hand-labeled sample. Do not attempt if it compromises the five core deliverables.

---

## End-to-End Data Flow

```
Prospect identified from Crunchbase ODM
  │
  ├─ Signal Enrichment Pipeline
  │    ├─ enrichment_brief.json         (firmographics, crunchbase_id)
  │    ├─ hiring_signal_brief.json      (funding, jobs, layoffs, leadership, AI maturity 0–3)
  │    └─ competitor_gap_brief.json     (top-quartile peers, prospect percentile, 2–3 gaps)
  │
  ├─ ICP Classifier
  │    └─ segment label + confidence score
  │         └─ below threshold → generic exploratory email only
  │
  ├─ LLM Agent composes signal-grounded email
  │    ├─ RAG over relevant seed materials injected into context
  │    ├─ tone-guard check vs style_guide.md (regenerate if fails)
  │    ├─ draft: true metadata applied
  │    └─ kill-switch checked (OUTBOUND_LIVE must be set)
  │
  ├─ Email sent via Resend / MailerSend
  │
  ├─ Prospect replies
  │    ├─ Warm → SMS scheduling via Africa's Talking (channel handoff)
  │    ├─ Agent qualifies via hiring_signal_brief
  │    │    └─ bench_summary checked before any capacity commitment
  │    ├─ Discovery call booked on Cal.com (both attendees on invite)
  │    └─ HubSpot contact record updated via MCP (all fields non-null, enrichment timestamp current)
  │
  └─ Every step traced to Langfuse
       └─ trace_id, cost, latency → trace_log.jsonl → evidence_graph.json
```

---

## Budget Envelope

| Layer | Cost | Notes |
|-------|------|-------|
| Resend / MailerSend (email) | $0 | 3,000 emails/month free |
| Africa's Talking (SMS) | $0 | Sandbox; virtual short codes |
| HubSpot Developer Sandbox | $0 | Free; 100 API calls / 10s |
| Cal.com self-hosted | $0 | Docker Compose |
| Langfuse cloud | $0 | Free tier; 50K traces |
| LLM dev tier — Days 1–4 | ≤ $4 | Qwen3 via OpenRouter |
| LLM eval tier — Days 5–7 | ≤ $6 | Claude Sonnet 4.6; 1 trial on held-out |
| Voice rig (bonus only) | ≤ $3/day | Auto rate-limited by rig |
| **Total** | **≤ $10 per trainee** | Overages must be documented in memo |

---

## Repository Structure

```
The_Conversion_Engine/
├── ARCHITECTURE.md
├── README.md                         ← setup + kill-switch documentation
├── .env.example                      ← OUTBOUND_LIVE not set by default
│
├── seed/                             ← Tenacious source-of-truth materials (Day 0)
│   ├── icp_definition.md
│   ├── sales_deck.pdf
│   ├── case_studies/
│   ├── email_sequences/
│   ├── discovery_transcripts/
│   ├── pricing_sheet.md
│   ├── bench_summary.json
│   └── style_guide.md
│
├── agent/
│   ├── email_handler.py              ← Resend/MailerSend + reply webhook + kill-switch
│   ├── sms_handler.py                ← Africa's Talking + STOP/HELP/UNSUB + kill-switch
│   ├── hubspot_mcp.py                ← HubSpot MCP (9 tools)
│   ├── cal_booking.py                ← Cal.com booking flow
│   ├── tone_guard.py                 ← second model call vs style_guide.md
│   ├── thread_store.py               ← per-(company_id, contact_id) isolation
│   ├── enrichment/
│   │   ├── crunchbase.py             ← firmographic lookup → enrichment_brief.json
│   │   ├── job_posts.py              ← Playwright velocity scraper
│   │   ├── layoffs.py                ← layoffs.fyi parser
│   │   ├── leadership.py             ← CTO/VP Eng change detection
│   │   └── ai_maturity.py            ← 0–3 scorer with per-signal confidence
│   ├── icp_classifier.py             ← segment + confidence + abstention
│   ├── competitor_gap.py             ← top-quartile gap analysis → competitor_gap_brief.json
│   └── requirements.txt
│
├── eval/
│   ├── harness.py                    ← τ²-Bench wrapper → Langfuse + score_log.json
│   ├── score_log.json                ← staff baseline + your method results (with 95% CI)
│   ├── trace_log.jsonl               ← full τ²-Bench trajectories
│   └── baseline.md                   ← staff-provided baseline notes (max 400 words)
│
├── probes/
│   ├── probe_library.md              ← 30+ structured probes (Tenacious-specific)
│   ├── failure_taxonomy.md           ← grouped by category + trigger rates
│   └── target_failure_mode.md        ← highest-ROI failure + business-cost derivation
│
├── method/
│   ├── method.md                     ← mechanism, rationale, hyperparameters, 3 ablations
│   ├── ablation_results.json         ← pass@1, CI, cost, latency (3 conditions)
│   └── held_out_traces.jsonl         ← raw traces for all 3 conditions
│
├── memo/
│   ├── memo.pdf                      ← exactly 2 pages
│   └── evidence_graph.json           ← every memo claim → trace_id or invoice line
│
├── market_space/                     ← distinguished stretch goal only
│   ├── market_space.csv
│   ├── top_cells.md
│   └── methodology.md
│
└── docs/
    ├── TRP1 Challenge Week 10_ Conversion Engine for Sales Automation.docx
    └── Supporting Scenario of The Conversion Engine.docx
```

---

## Grading Observables (out of 18)

| Observable | What it checks | Tenacious-specific note | Pass | Distinguished |
|------------|---------------|------------------------|------|---------------|
| Reproduction fidelity | Day 1 baseline matches pinned reference | Automated re-run under pinned model/settings | ≥1 | 3 |
| Probe originality | Probes diagnostic of specific Tenacious failure modes | Must be Tenacious-specific, not generic B2B | ≥1 | 3 |
| Mechanism attribution | Ablation proves mechanism caused the lift (Delta A, p < 0.05) | Automated statistical check on held_out_traces.jsonl | ≥1 | 3 |
| Cost-quality Pareto | Cost per qualified lead ≤ $5; hard penalty > $8 | Per qualified lead, not per message | ≥1 | 3 |
| Evidence-graph integrity | Every memo number resolves to trace file or Tenacious-provided number | Fabricated Tenacious numbers = disqualifying violation | ≥1 | 3 |
| Skeptic's appendix quality | Tenacious-specific risks: brand reputation, bench mismatch, offshore-perception objections | Generic risks ("user adoption is hard") are penalized | ≥1 | 3 |

**Passing:** 12+ with no single observable below 1
**Distinguished:** 15+ with at least three observables at 3

---

## Deadlines

| Milestone | Date | Deliverables |
|-----------|------|-------------|
| Interim submission | 2026-04-22 21:00 UTC | GitHub repo + PDF (Acts I & II complete) |
| Final submission | 2026-04-25 21:00 UTC | GitHub repo + memo.pdf (2 pages) + demo video (max 8 min, no login required) |

### Demo Video Checklist (max 8 minutes)
- [ ] Live email conversation end-to-end (signal-grounded outreach → reply → qualification → Cal.com booking)
- [ ] hiring_signal_brief + competitor_gap_brief visible with per-signal confidence scores
- [ ] HubSpot contact record populating in real time (all fields non-null, timestamp current)
- [ ] Email → SMS channel handoff for warm scheduling coordination
- [ ] Agent refusing to over-claim when < 5 open roles (honesty constraint live)
- [ ] Agent correctly handling a post-layoff + recently-funded company (cross-signal segment routing)
- [ ] τ²-Bench harness producing a score with query trace visible
- [ ] Walkthrough of probe library showing at least one probe that led to a concrete fix
- [ ] *(Bonus)* One real voice call end-to-end through Shared Voice Rig
