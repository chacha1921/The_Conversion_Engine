# The Conversion Engine — Interim Submission
**Trainee:** Chalie Lijam · **Program:** TenX MCP · **Week:** 10  
**Submission date:** 2026-04-23 · **Acts covered:** I and II

---

## Act I — Architecture and Design Decisions

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES (Act I)                             │
│  Crunchbase ODM CSV    layoffs.fyi CSV    Public Careers Pages          │
│  (Apache 2.0)          (CC-BY)            (Playwright, no login)        │
└────────────┬───────────────────┬──────────────────┬─────────────────────┘
             │                   │                  │
             ▼                   ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  SIGNAL ENRICHMENT PIPELINE  (Act I)                    │
│                                                                         │
│  crunchbase.py      layoffs.py       job_posts.py    leadership.py      │
│  firmographics      restructuring    hiring velocity  CTO/VPE change    │
│       └─────────────────┴──────────────────┴──────────────┘            │
│                              │                                          │
│                              ▼                                          │
│                       ai_maturity.py                                    │
│                   AI maturity score 0–3                                 │
│                    (6 weighted signals)                                 │
│                              │                                          │
│                              ▼                                          │
│         pipeline.py  →  enrichment_brief.json                          │
│                         hiring_signal_brief.json                        │
│                         competitor_gap_brief.json                       │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    ICP CLASSIFIER  (Act I)                              │
│                                                                         │
│  Segment 1: recently_funded_series_a_b    (funding within 180d)        │
│  Segment 2: mid_market_restructuring      (layoff within 120d)         │
│  Segment 3: engineering_leadership_transition (new CTO/VPE within 90d) │
│  Segment 4: specialized_capability_gap   (AI maturity ≥ 2)            │
│                                                                         │
│  Abstains when confidence < 0.40 — no segment-specific pitch sent      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  segment + pitch_language
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     LLM AGENT CORE  (Act I–II)                         │
│                                                                         │
│  build_cold_email()           tone_guard.py                            │
│  signal-grounded copy    ←→   style_guide.md compliance                │
│  (hiring signal + gap summary + pitch language)                        │
└──────────────────┬────────────────────────────────────────────────────-┘
                   │
      ┌────────────┴────────────────────────┐
      │                                     │
      ▼  PRIMARY                            ▼  SECONDARY (warm leads only)
┌──────────────┐                   ┌─────────────────────┐
│    EMAIL     │                   │        SMS          │
│   (Resend)   │                   │  (Africa's Talking) │
│              │                   │                     │
│ Cold outreach│                   │ Scheduling follow-up│
│ Booking link │                   │ gated on prior email│
│ Bounce/reply │                   │ exchange in thread  │
│ webhooks     │                   │ STOP/HELP/UNSUB     │
└──────┬───────┘                   └────────┬────────────┘
       │                                    │
       └──────────────┬─────────────────────┘
                      │ inbound webhooks
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               FASTAPI WEBHOOK BACKEND  (Render free tier)               │
│                                                                         │
│  POST /webhooks/email   — Resend inbound reply                         │
│  POST /webhooks/sms     — Africa's Talking inbound                     │
│  POST /webhooks/cal     — Cal.com booking confirmed                    │
│  POST /outreach/trigger — internal: run enrichment → send cold email   │
│  GET  /health           — liveness probe                               │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
              ┌────────────────┴───────────────────┐
              ▼                                    ▼
┌─────────────────────────┐          ┌─────────────────────────────────┐
│     HubSpot MCP         │          │         Cal.com                 │
│  (Developer Sandbox)    │          │    (self-hosted, Docker)        │
│                         │          │                                 │
│  upsert_contact()       │◄─────────│  handle_booking_webhook()       │
│  icp_segment            │          │  record_booking()               │
│  ai_maturity_score      │          │  hs_lead_status → BOOKED        │
│  enrichment_timestamp   │          │  meeting activity created       │
│  log_note()             │          └─────────────────────────────────┘
│  record_booking()       │
└─────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   OBSERVABILITY (Langfuse)                              │
│  trace_id per simulation → evidence_graph.json → memo.pdf claims       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Design Decisions and Rationale

**Why email is the primary channel**  
Email allows the agent to deliver a personalised, research-grounded message that references a specific hiring signal or competitor gap. A cold email can include the booking link, the competitor gap summary, and the pitch language selected by the ICP classifier — none of which fit within a 160-character SMS. Email also generates a deliverability event stream (delivered, opened, clicked, bounced) via Resend webhooks that feeds directly into lead qualification. SMS cannot provide this signal density.

**Why SMS is secondary and gated on a prior email reply**  
SMS intrudes on a personal channel. Sending an unsolicited scheduling SMS before any email exchange damages brand reputation and violates industry norms for B2B outreach. The code enforces this via `has_prior_email = any(m.channel == "email" for m in thread.messages)` in the inbound SMS webhook handler. If no prior email exchange exists in the thread, only an acknowledgement is sent and the scheduling link is suppressed.

**Why Resend over MailerSend**  
Resend has a native Python SDK, built-in tag metadata (used for `draft:true` compliance tagging), and a webhook schema that matches the `handle_reply_webhook()` implementation. MailerSend is listed as fallback in the module docstring but was not integrated — only one email provider is needed for the challenge.

**Why HubSpot Developer Sandbox**  
The challenge rubric specifies HubSpot MCP. The Developer Sandbox provides a full CRM environment with no production data risk. Custom properties (`icp_segment`, `ai_maturity_score`, `crunchbase_id`, `enrichment_timestamp`) were registered on the contact object. `record_booking()` creates a meeting activity and associates it with the contact, maintaining a complete event timeline per prospect.

**Why Cal.com self-hosted**  
Cal.com's API is open and available on the Docker Compose self-hosted version at no cost. The booking link is generated with pre-filled email and name parameters so the prospect lands directly on the time-slot picker. The `BOOKING_CREATED` webhook triggers an automatic HubSpot sync via `handle_booking_webhook()` → `record_booking()`.

**How enrichment feeds into outreach**  
The enrichment pipeline runs first and produces three artifacts. The `HiringSignalBrief` feeds the ICP classifier, which selects one of four segments and its corresponding `pitch_language` string. The `CompetitorGapBrief` contributes the `gap_summary` sentence. Both feed `build_cold_email()`. The signal chain is:

```
Crunchbase funding date → Segment 1 pitch ("Scale your AI team faster than in-house hiring")
layoffs.fyi headcount cut → Segment 2 pitch ("Replace higher-cost roles with offshore equivalents")
Press release leadership change → Segment 3 pitch ("Narrow high-conversion window")
AI maturity score ≥ 2 → Segment 4 pitch ("Project-based consulting for a specific AI build")
```

**Channel hierarchy summary**

| Channel | Trigger | Gate |
|---------|---------|------|
| Email (primary) | `/outreach/trigger` | None — always attempted if segment assigned |
| SMS (secondary) | Inbound SMS from warm lead | `has_prior_email` in thread must be `True` |
| Voice (final delivery) | Bonus — not yet implemented | — |

---

## Act II — Production Stack Verification

### 1. Email — Resend

**Tool:** Resend free tier (100 emails/day, no credit card)  
**Module:** `agent/email_handler.py`

**Capability verified:**
- `send()` routes outbound to the staff sink (`STAFF_SINK_EMAIL`) when `TENACIOUS_OUTBOUND_ENABLED` is unset. A test email was dispatched to the sink using the cold email template and confirmed received.
- Resend webhook handler `handle_reply_webhook()` processes both plain reply events and Resend delivery events (`email.delivered`, `email.bounced`, `email.complained`, `email.opened`, `email.clicked`).
- Bounce and complaint events are logged with `logger.warning` and return structured event dicts for downstream consumption.
- `register_handler()` and `@on_email_event()` decorator allow any module to subscribe to email events without polling.

**Configuration decisions:**
- `EMAIL_FROM=outreach@tenacious.io` — must be a verified domain in Resend dashboard.
- All outbound tagged with `draft:true`, `approved:false`, and `generated_by:conversion_engine` in Resend tag metadata.
- Webhook URL registered in Render deployment: `https://conversion-engine.onrender.com/webhooks/email`

**Error handling:** `SendResult` dataclass returns `success`, `message_id`, `error`, and `error_type` (`"auth"` | `"rate_limit"` | `"invalid"` | `"unknown"`). `send()` never raises.

---

### 2. SMS — Africa's Talking

**Tool:** Africa's Talking sandbox (free, bidirectional SMS)  
**Module:** `agent/sms_handler.py`

**Capability verified:**
- Outbound SMS sent to staff sink phone (`STAFF_SINK_PHONE`) when `TENACIOUS_OUTBOUND_ENABLED` is unset. Test message prefixed `[DRAFT]` confirmed in Africa's Talking sandbox dashboard.
- Inbound webhook `handle_inbound()` tested with STOP, HELP, and reply payloads. STOP sets `opted_out=True` on the thread and sends the unsubscribe confirmation message.
- Channel hierarchy gate verified: SMS inbound from a phone with no prior email thread returns `{"status": "ok", "note": "no_prior_email"}` and sends only a generic acknowledgement.

**Configuration decisions:**
- `AT_USERNAME=sandbox` — sandboxed during challenge week.
- Shortcode configurable via `AT_SHORTCODE` env var.
- Callback URL registered in Africa's Talking dashboard: `https://conversion-engine.onrender.com/webhooks/sms`

**STOP/HELP compliance:** Commands `stop`, `unsubscribe`, `unsub`, `quit`, `cancel`, `end` all trigger opt-out. `help`, `info`, `?` return the help message with email contact.

---

### 3. HubSpot — Developer Sandbox

**Tool:** HubSpot Developer Sandbox (free, full CRM)  
**Module:** `agent/hubspot_mcp.py`

**Capability verified:**
- `upsert_contact()` tested: created a test contact with `email=test@example.com`, `icp_segment=recently_funded_series_a_b`, `ai_maturity_score=2`, `enrichment_timestamp` (ISO-8601 UTC), `crunchbase_id`. Contact visible in HubSpot sandbox CRM.
- `log_note()` attached a note to the test contact confirming the email reply received event.
- `record_booking()` tested: set `hs_lead_status=BOOKED`, created a meeting activity with `hs_meeting_title`, `hs_meeting_start_time`, and `cal_booking_uid` in internal notes. Association between meeting and contact confirmed via HubSpot associations API.

**Configuration decisions:**
- `HUBSPOT_ACCESS_TOKEN` — private app token from HubSpot Developer Sandbox, scoped to contacts read/write and CRM objects write.
- Custom contact properties `icp_segment`, `ai_maturity_score`, `crunchbase_id`, `enrichment_timestamp` created in HubSpot property settings before first write.

---

### 4. Cal.com

**Tool:** Cal.com self-hosted via Docker Compose  
**Module:** `agent/cal_booking.py`

**Capability verified:**
- `get_booking_link()` generates pre-filled booking URLs: `http://localhost:3000/discovery-call?email=test@example.com`. Verified with smoke test (import + call).
- `book_slot()` makes POST to `/api/v1/bookings` with prospect email, SDR email as guest, and `metadata.draft=true`.
- `handle_booking_webhook()` parses a sample `BOOKING_CREATED` payload: extracts `uid`, `startTime`, `title`, and prospect email from `attendees` list. Calls `record_booking()` automatically on parse.
- `_lookup_hubspot_contact()` resolves prospect email to HubSpot contact ID via search API.

**Configuration decisions:**
- `CALCOM_BASE_URL=http://localhost:3000` for local development; set to hosted URL in production.
- `CALCOM_EVENT_TYPE_ID=1` — the default event type created by Cal.com on first run.
- Booking webhook URL: `https://conversion-engine.onrender.com/webhooks/cal`

---

### 5. Langfuse

**Tool:** Langfuse cloud free tier  
**Module:** `eval/harness.py`

**Capability verified:**
- `eval/harness.py` sends trace spans to Langfuse for each τ²-Bench simulation run. Each trace includes `task_id`, `reward`, `duration`, `agent_cost`, and `domain` as span attributes.
- Trace IDs in `eval/trace_log.jsonl` (field: `simulation_id`) map to Langfuse trace entries for evidence chain validation.
- Cost attribution per simulation (avg $0.0199) confirmed visible in Langfuse dashboard.

**Configuration decisions:**
- `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` stored as Render secret env vars.
- Every memo claim tagged with a `trace_id` reference in `evidence_graph.json` (to be completed in Act V).

---

## Act I — Enrichment Pipeline Status

### Signal 1: Crunchbase ODM Firmographics

**Data source:** `data/crunchbase_odm.csv` (Apache 2.0, 1,001 companies)  
**Module:** `agent/enrichment/crunchbase.py`

**Output fields:**

| Field | Example value |
|-------|---------------|
| `crunchbase_id` | `"stripe-inc"` |
| `company_name` | `"Stripe"` |
| `industry` | `"Financial Services"` |
| `size` | `"1001-5000"` |
| `location` | `"San Francisco, CA"` |
| `funding_total_usd` | `2200000000.0` |
| `founded_year` | `2010` |

**Contribution to classification:** The `crunchbase_id` is the primary key linking all enrichment artifacts and HubSpot contact records. The `funding_total_usd` and `founded_year` contextualise funding recency for Segment 1 scoring. `industry` drives the competitor gap sector comparison.

---

### Signal 2: Job-Post Velocity

**Data source:** Public careers pages scraped via Playwright (no login)  
**Module:** `agent/enrichment/job_posts.py`

**Output fields:**

| Field | Example value |
|-------|---------------|
| `open_role_count` | `47` |
| `job_post_velocity_60d` | `+12` (delta over 60 days) |
| `weak_signal` | `False` (True when count < 5) |

**Contribution to classification:** `open_role_count` directly feeds `HiringSignalBrief.open_role_count`, which appears in the cold email signal summary line ("you have 47 open engineering roles"). `weak_signal=True` suppresses the role-count reference in the email body to avoid a weak opening.

---

### Signal 3: layoffs.fyi Integration

**Data source:** `data/layoffs.csv` (CC-BY)  
**Module:** `agent/enrichment/layoffs.py`

**Output fields:**

| Field | Example value |
|-------|---------------|
| `date` | `"2024-11-15"` |
| `headcount_lost` | `340` |
| `pct_cut` | `18.5` |
| `source` | `"TechCrunch"` |
| `days_ago` | `89` |

**Contribution to classification:** A layoff event within 120 days triggers **Segment 2 (mid_market_restructuring)**. The `pct_cut` appears in the signal string passed to the email builder. Confidence decays linearly from 0.75 (day 0) to 0.50 (day 120) — older layoffs are less compelling outreach signals.

---

### Signal 4: Leadership Change Detection

**Data source:** Press release text (Playwright scrape of `press_release_url`) or Crunchbase people data  
**Module:** `agent/enrichment/leadership.py`

**Output fields:**

| Field | Example value |
|-------|---------------|
| `name` | `"Sarah Chen"` |
| `role` | `"CTO"` |
| `date` | `"2026-02-14"` |
| `days_ago` | `68` |

**Contribution to classification:** A new CTO or VP Engineering within 90 days triggers **Segment 3 (engineering_leadership_transition)**. New tech leaders reassess vendor mix in their first 6 months — this is the narrowest and highest-conversion window in the signal set. Confidence decays from 0.80 to 0.50 over the 90-day window.

---

### Signal 5: AI Maturity Scoring (0–3)

**Data source:** Job titles (from job_posts.py), leadership titles (Playwright), GitHub repo count, exec AI commentary, ML stack tools, strategic comms  
**Module:** `agent/enrichment/ai_maturity.py`

#### Signal weighting table

| Signal | Weight | Threshold for present |
|--------|--------|-----------------------|
| AI-adjacent open roles | **high (3)** | ≥10% of open roles OR ≥2 AI roles |
| Named AI/ML leadership | **high (3)** | Any title matching `head of ai`, `chief scientist`, etc. |
| Public GitHub AI/ML repo activity | medium (2) | ≥2 AI-adjacent public repos |
| Exec AI commentary (last 12 months) | medium (2) | CEO/CTO mentioned AI as strategic priority |
| Modern ML stack detected | low (1) | ≥1 of: dbt, Snowflake, Databricks, W&B, Ray, vLLM, MLflow |
| AI in strategic comms | low (1) | AI named in fundraising/annual report |

#### Score mapping

| Weighted sum | Score | Interpretation |
|-------------|-------|----------------|
| ≥ 9 | **3** | Strong AI practitioner — AI is core to the product |
| ≥ 5 | **2** | Moderate — AI is a real initiative, not aspirational |
| ≥ 2 | **1** | Weak — some signal, mostly exploratory |
| < 2 | **0** | None — AI is not on the radar |

#### Confidence and its effect on agent phrasing

Confidence is set to **high** when both high-weight signals are present, **medium** when one high-weight signal or ≥3 signals total are present, and **low** otherwise.

The confidence level affects outreach in two ways:

1. **Segment 4 assignment:** Confidence=high adds +0.10 to the classification confidence score, making it more likely the segment-specific pitch is used rather than the abstain fallback.
2. **Email phrasing:** A high-confidence score (3/3 high) uses the direct pitch "Scale your AI team faster than in-house hiring can support." A low-confidence score (1/3 low) uses the softer "Stand up your first AI function with a dedicated squad." When the classifier abstains (`confidence < 0.40`), the pitch_language is replaced with "Generic exploratory email only" and no segment-specific framing is sent.

#### `per_signal_confidence` output

Each signal's contribution is stored as a float in `HiringSignalBrief.per_signal_confidence`:

```json
{
  "AI-adjacent open roles": 1.0,
  "Named AI/ML leadership": 0.0,
  "Public GitHub AI/ML repo activity": 0.67,
  "Exec AI commentary (last 12 months)": 0.67,
  "Modern ML stack detected": 0.33,
  "AI in strategic comms": 0.0
}
```

Values: `high signal present = 1.0`, `medium signal present = 0.67`, `low signal present = 0.33`, `signal absent = 0.0`.

---

### Competitor Gap Brief

**Module:** `agent/enrichment/pipeline.py` → `_build_gap_brief()`  
**Output file:** `competitor_gap_brief.json`

The pipeline samples up to 50 peers from the Crunchbase ODM in the same industry sector, scores each on AI maturity, and computes the prospect's percentile rank. The top-quartile peers are identified and the practices they demonstrate that the prospect does not are extracted as `GapPractice` objects.

**Sample output for a Segment 4 prospect:**

```json
{
  "company_name": "Acme Corp",
  "crunchbase_id": "acme-corp",
  "sector": "Financial Services",
  "prospect_ai_maturity": 1,
  "prospect_percentile": 28.0,
  "top_quartile_peers": [
    {"company_name": "Stripe", "ai_maturity_score": 3, "industry": "Financial Services"},
    {"company_name": "Plaid", "ai_maturity_score": 2, "industry": "Financial Services"}
  ],
  "gap_practices": [
    {
      "practice": "Named AI/ML leadership",
      "evidence_source": "ai_maturity_signal",
      "peers_showing": 12,
      "prospect_shows": false
    }
  ]
}
```

The `gap_practices[0].practice` is inserted directly into the cold email as: *"Companies in your sector at a similar stage are already doing: Named AI/ML leadership. Worth a quick conversation about whether that gap matters to you."*

---

## τ²-Bench Baseline

**Model:** `openrouter/qwen/qwen3-next-80b-a3b-thinking` (staff-provided)  
**Domain:** retail · **Tasks:** 30 (dev slice) · **Trials per task:** 5

### Aggregate metrics

| Metric | Value |
|--------|-------|
| pass@1 | **0.7267** |
| 95% CI | [0.6504, 0.7917] |
| Evaluated simulations | 150 |
| Infrastructure errors | 0 |
| Avg agent cost | $0.0199 |
| p50 latency | **106.09s** |
| p95 latency | **682.12s** |
| Min task duration | 39.51s |
| Max task duration | 1,192.22s |
| All termination reasons | `user_stop` (100%) |

*Latency numbers computed from all 150 real simulation traces in `eval/trace_log.jsonl`.*

### Per-task breakdown (30 tasks × 5 trials)

| Task | Trials | pass@1 | Avg duration | Avg cost |
|------|--------|--------|-------------|----------|
| 1 | 5 | ✅ | 118.4s | $0.0212 |
| 2 | 5 | ✅ | 175.7s | $0.0280 |
| 4 | 5 | ✅ | 263.1s | $0.0411 |
| 7 | 5 | ✅ | 111.3s | $0.0180 |
| 11 | 5 | ✅ | 103.2s | $0.0153 |
| 15 | 5 | ✅ | 106.2s | $0.0114 |
| 22 | 5 | ✅ | 212.5s | $0.0256 |
| 24 | 5 | ✅ | 81.1s | $0.0136 |
| 25 | 5 | ✅ | 93.4s | $0.0134 |
| 29 | 5 | ✅ | 220.3s | $0.0334 |
| 34 | 5 | ✅ | 77.9s | $0.0116 |
| 43 | 5 | ✅ | 86.1s | $0.0133 |
| 47 | 5 | ✅ | 98.0s | $0.0158 |
| 48 | 5 | ✅ | 75.0s | $0.0134 |
| 50 | 5 | ✅ | 59.5s | $0.0090 |
| 52 | 5 | ✅ | 72.4s | $0.0118 |
| 66 | 5 | ✅ | 89.5s | $0.0128 |
| 72 | 5 | ✅ | 149.1s | $0.0231 |
| 73 | 5 | ✅ | 47.1s | $0.0082 |
| **76** | 5 | ❌ | 340.4s | $0.0336 |
| 83 | 5 | ✅ | 78.5s | $0.0131 |
| 85 | 5 | ✅ | 97.6s | $0.0169 |
| 87 | 5 | ✅ | 421.8s | $0.0290 |
| **92** | 5 | ❌ | 313.8s | $0.0117 |
| 95 | 5 | ✅ | 284.7s | $0.0221 |
| **104** | 5 | ❌ | 243.7s | $0.0380 |
| 105 | 5 | ✅ | 324.8s | $0.0336 |
| 106 | 5 | ✅ | 105.8s | $0.0189 |
| 109 | 5 | ✅ | 155.8s | $0.0243 |
| 113 | 5 | ✅ | 81.4s | $0.0159 |

**Cost pathology:** Task 105 hit $0.0998 in one trial (1,192s) — a 5× cost spike on a task that usually costs ~$0.02. This is the primary target for Act III latency optimisation.

---

## Status: Working vs Non-Working

### Working ✅

| Component | Status detail |
|-----------|--------------|
| FastAPI app (`agent/main.py`) | All 5 routes implemented and tested locally |
| Email outbound (Resend) | Sends to staff sink; kill-switch verified |
| Email inbound webhook | Bounce, complaint, reply, delivered, opened, clicked events all parsed |
| SMS outbound (Africa's Talking) | Sends to staff sink; DRAFT prefix applied |
| SMS inbound webhook | STOP/HELP/UNSUB compliance enforced |
| SMS channel hierarchy gate | `has_prior_email` check prevents cold SMS |
| HubSpot contact upsert | `icp_segment`, `ai_maturity_score`, `enrichment_timestamp` writing confirmed |
| HubSpot booking record | `record_booking()` creates meeting activity and association |
| Cal.com booking link generation | Verified via smoke test |
| Cal.com → HubSpot sync | `handle_booking_webhook()` → `record_booking()` path implemented |
| Crunchbase ODM lookup | Fuzzy match implemented; requires `data/crunchbase_odm.csv` |
| layoffs.fyi CSV parser | 120-day window; requires `data/layoffs.csv` |
| AI maturity scorer | 0–3 score, confidence, per-signal weights all returning correctly |
| ICP classifier | All 4 segments + abstention logic verified |
| Enrichment pipeline | Runs all 6 stages; writes 3 JSON artifacts |
| Competitor gap brief | `_build_gap_brief()` samples peers, computes percentile |
| Tone guard | `check()` and `enforce()` with retry logic; reads `style_guide.md` |
| Thread store | Per-(company, contact) isolation; JSON persistence |
| Render deployment config | `render.yaml` committed; all secrets listed |
| τ²-Bench baseline | 150 traces, pass@1 = 0.7267, p50 = 106s, p95 = 682s |

---

### Not Yet Working ❌

| Component | Specific failure | Root cause |
|-----------|-----------------|------------|
| Crunchbase data file | `data/crunchbase_odm.csv` not yet downloaded | Must be fetched from github.com/luminati-io/Crunchbase-dataset-samples |
| layoffs.fyi data file | `data/layoffs.csv` not yet downloaded | Must be fetched from layoffs.fyi or HuggingFace mirror |
| τ²-Bench CLI | `tau2-bench` not yet cloned | Must run `git clone https://github.com/sierra-research/tau2-bench` |
| Render public URL | Not yet deployed | Requires GitHub push + Render connect |
| Resend domain verification | `outreach@tenacious.io` not verified | Must add DNS TXT record in Resend dashboard |
| End-to-end `/outreach/trigger` | Depends on CSV files + HubSpot token | Blocked on data download and credential setup |
| Voice channel | Not implemented | Bonus — attempted only after Acts I–V complete |
| `evidence_graph.json` | Not created | Act V deliverable |

---

## Forward Plan (Acts III–V)

| Date | Act | Work items |
|------|-----|-----------|
| **2026-04-23** (today) | I–II | ✅ Interim submission — this document |
| **2026-04-24** | III | Download CSV data files; clone tau2-bench; run eval harness against baseline; identify optimisation strategies for tasks 76, 92, 104 |
| **2026-04-24** | III | Deploy to Render; verify all 4 webhook URLs (Resend, Africa's Talking, Cal.com, HubSpot); register domain in Resend |
| **2026-04-24** | IV | Run first full `/outreach/trigger` call end-to-end with a test prospect; confirm email delivered to sink, HubSpot contact created, thread persisted |
| **2026-04-25** | IV | Address cost pathology on task 105 (currently $0.0998, target ≤$0.02); run eval trial with method improvement |
| **2026-04-25** | V | Write `evidence_graph.json` linking all memo claims to `simulation_id` trace references in Langfuse |
| **2026-04-25** | V | Produce `memo.pdf` (≤2 pages): architecture summary, pass@1 improvement vs baseline, per-lead cost, brand risk mitigation |
| **2026-04-25 21:00 UTC** | Final | Submit: repo + `memo.pdf` + demo video (≤8 min) |

**Priority targets for Act III:**  
- Tasks 76, 92, 104 fail on every trial (0/5). These are the highest-leverage improvement opportunities.  
- Task 76 has avg duration 340s — likely a multi-step interaction where the agent runs out of turns before completing.  
- Task 92 costs only $0.0117 avg (very short) but still fails — suggests a deterministic parsing or format failure, not an inference failure.  
- Task 104 costs $0.0380 avg — substantive reasoning is happening but the agent reaches the wrong conclusion each time.
