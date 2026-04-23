# The Conversion Engine

An Automated Lead Generation and Conversion System for Tenacious Consulting and Outsourcing.

> **System character:** This is not only a qualifier — it is a researcher. The most successful
> outputs produce a grounded view of a prospect's AI maturity, a comparison against the
> top quartile of their sector, and a specific gap worth a 30-minute conversation.

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system diagram and component details.

```
Data Sources (Crunchbase ODM, layoffs.fyi, Public Job Posts)
  → Signal Enrichment Pipeline  (enrichment_brief + hiring_signal_brief + competitor_gap_brief)
  → ICP Classifier              (Segment 1–4 with confidence + abstention)
  → LLM Agent Core              (signal-grounded, bench-gated, tone-guarded)
  → Email (primary) → SMS (secondary) → Voice (bonus)
  → HubSpot MCP + Cal.com + Langfuse
  → τ²-Bench Evaluation Layer
```

---

## Production Stack Status

| Layer | Tool | Status |
|-------|------|--------|
| **Webhook backend** | **Render free tier** | **`render.yaml` — stable public URL for all 4 integrations** |
| Email (primary) | Resend free tier | Integrated — `agent/email_handler.py` |
| SMS (secondary) | Africa's Talking sandbox | Integrated — `agent/sms_handler.py` |
| CRM | HubSpot Developer Sandbox (MCP) | Integrated — `agent/hubspot_mcp.py` |
| Calendar | Cal.com self-hosted (Docker) | Integrated — `agent/cal_booking.py` |
| Observability | Langfuse cloud free tier | Integrated — `eval/harness.py` |
| LLM dev tier | OpenRouter Qwen3 | Configured via `.env` |
| LLM eval tier | Claude Sonnet 4.6 | Configured via `.env` |

---

## Enrichment Pipeline Status

| Signal | Module | Output |
|--------|--------|--------|
| Crunchbase firmographics | `agent/enrichment/crunchbase.py` | `enrichment_brief.json` |
| Job-post velocity (60-day delta) | `agent/enrichment/job_posts.py` | included in `hiring_signal_brief.json` |
| layoffs.fyi integration | `agent/enrichment/layoffs.py` | included in `hiring_signal_brief.json` |
| Leadership-change detection | `agent/enrichment/leadership.py` | included in `hiring_signal_brief.json` |
| AI maturity scoring (0–3) | `agent/enrichment/ai_maturity.py` | `hiring_signal_brief.json` |
| Competitor gap brief | `agent/enrichment/pipeline.py` | `competitor_gap_brief.json` |

---

## τ²-Bench Baseline

Provided by program staff. Model: `openrouter/qwen/qwen3-next-80b-a3b-thinking`.

| Metric | Value |
|--------|-------|
| pass@1 | 0.7267 |
| 95% CI | [0.6504, 0.7917] |
| Avg agent cost | $0.0199 |
| p50 latency | 105.95s |
| p95 latency | 551.65s |
| Tasks | 30 (dev slice) |

Full trace: `eval/trace_log.jsonl` · Score log: `eval/score_log.json` · Notes: `eval/baseline.md`

---

## Setup Instructions

### Prerequisites
- Python 3.12
- Docker (for Cal.com)
- Africa's Talking sandbox account
- Resend or MailerSend free account
- HubSpot Developer Sandbox
- Langfuse cloud account (free tier)

### 1. Clone and install

```bash
git clone <repo-url>
cd The_Conversion_Engine
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in all values in .env
# OUTBOUND_LIVE is intentionally left unset — routes to staff sink by default
```

### 3. Download data files

```bash
mkdir -p data
# Crunchbase ODM (Apache 2.0):
# Download from github.com/luminati-io/Crunchbase-dataset-samples
# Save as: data/crunchbase_odm.csv

# layoffs.fyi (CC-BY):
# Download from layoffs.fyi or HuggingFace mirror
# Save as: data/layoffs.csv
```

### 4. Add seed materials

```bash
# Seed materials are delivered via the private program repo on Day 0.
# Place them in the seed/ directory:
# seed/icp_definition.md
# seed/sales_deck.pdf
# seed/style_guide.md
# seed/bench_summary.json
# seed/pricing_sheet.md
# seed/email_sequences/
# seed/case_studies/
# seed/discovery_transcripts/
```

### 5. Start Cal.com

```bash
# In a separate terminal:
git clone https://github.com/calcom/cal.com.git
cd cal.com
cp .env.example .env  # configure
docker compose up
```

### 6. Run the API server (local)

```bash
source .venv/bin/activate
uvicorn agent.main:app --reload --port 8000
```

### 7. Deploy to Render (webhook backend)

Render provides a stable public URL — required so Resend, Africa's Talking, and Cal.com can
reach your webhook endpoints. No credit card required.

```
1. Push this repo to GitHub
2. Go to https://render.com → New → Web Service → Connect your repo
3. Render auto-detects render.yaml and pre-fills all settings
4. Add secret env vars in the Render dashboard (all marked sync: false in render.yaml):
     RESEND_API_KEY, AT_API_KEY, HUBSPOT_ACCESS_TOKEN, CALCOM_API_KEY,
     LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, OPENROUTER_API_KEY,
     STAFF_SINK_EMAIL, STAFF_SINK_PHONE, SDR_EMAIL, CALCOM_BASE_URL
5. Deploy — Render returns a URL like: https://conversion-engine.onrender.com

Register that URL once across all four integrations:
  • Resend:            Dashboard → Webhooks → https://<your-url>/webhooks/email
  • Africa's Talking:  Dashboard → SMS → Callback URL → https://<your-url>/webhooks/sms
  • Cal.com:           Admin → Webhooks → https://<your-url>/webhooks/cal
  • HubSpot:           (events flow outbound only; no inbound webhook needed)

OUTBOUND_LIVE is intentionally NOT set in render.yaml — all outbound routes to the
staff sink until you add that env var in the Render dashboard and get staff approval.
```

### 8. Trigger a test outreach

```bash
curl -X POST http://localhost:8000/outreach/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Corp",
    "prospect_email": "test@example.com",
    "prospect_name": "Test Prospect",
    "careers_url": "https://acme.com/careers"
  }'
```

---

## Kill-Switch

**OUTBOUND_LIVE is unset by default.** All outbound (email + SMS) routes to the staff sink.

To enable live outbound (only after program staff approval):

```bash
export OUTBOUND_LIVE=true
```

This flag must be explicitly set at the email handler, SMS handler, and voice handler levels.
Any code review that finds outbound routes bypassing this check is a disqualifying violation.

---

## Repository Structure

```
The_Conversion_Engine/
├── README.md
├── ARCHITECTURE.md
├── Dockerfile
├── render.yaml                    ← Render free-tier deploy config (webhook backend)
├── requirements.txt
├── .env.example
├── .gitignore
│
├── agent/
│   ├── main.py                    ← FastAPI app (email + SMS webhooks, outreach trigger)
│   ├── email_handler.py           ← Resend integration + kill-switch
│   ├── sms_handler.py             ← Africa's Talking + STOP/HELP/UNSUB
│   ├── hubspot_mcp.py             ← HubSpot CRM writes
│   ├── cal_booking.py             ← Cal.com booking flow
│   ├── icp_classifier.py          ← Segment assignment + confidence + abstention
│   ├── tone_guard.py              ← style_guide.md compliance check
│   ├── thread_store.py            ← Per-(company, contact) conversation isolation
│   └── enrichment/
│       ├── models.py              ← Pydantic models for all three briefs
│       ├── crunchbase.py          ← Firmographic lookup → enrichment_brief.json
│       ├── job_posts.py           ← Playwright job-post velocity scraper
│       ├── layoffs.py             ← layoffs.fyi parser
│       ├── leadership.py          ← CTO/VP Eng change detection
│       ├── ai_maturity.py         ← 0–3 scorer with per-signal confidence
│       └── pipeline.py            ← Full enrichment orchestrator
│
├── eval/
│   ├── harness.py                 ← τ²-Bench wrapper → Langfuse + score_log.json
│   ├── score_log.json             ← Staff baseline + method results
│   ├── trace_log.jsonl            ← 150 raw simulation traces (staff baseline)
│   └── baseline.md                ← Baseline notes (staff-provided)
│
├── data/                          ← Local data files (gitignored except structure)
│   ├── crunchbase_odm.csv         ← Download separately (Apache 2.0)
│   └── layoffs.csv                ← Download separately (CC-BY)
│
└── docs/                          ← Challenge documents (gitignored)
```

---

## Budget

| Layer | Cost |
|-------|------|
| Email, SMS, CRM, Calendar, Observability | $0 (free tiers) |
| LLM dev tier (Days 1–4) | ≤ $4 |
| LLM eval tier (Days 5–7) | ≤ $6 |
| Voice rig (bonus) | ≤ $3/day |
| **Total** | **≤ $10** |

---

## Data Handling

- No real Tenacious customer data is stored in this repo
- All seed materials (sales deck, case studies, pricing sheet) are gitignored and must be deleted from personal infrastructure at end of challenge week
- All synthetic prospects during the challenge week route to the staff sink by default
- Any Tenacious-branded agent output is tagged `draft: true` in metadata

---

## Deadlines

| Milestone | Date | Deliverables |
|-----------|------|-------------|
| Interim | 2026-04-23 23:59 UTC | This repo + PDF (Acts I & II) |
| Final | 2026-04-25 21:00 UTC | Repo + memo.pdf (2 pages) + demo video (max 8 min) |
