# Probe Library — Tenacious Conversion Engine
<!-- 33 structured probes. All are Tenacious-specific, not generic B2B. -->
<!-- Each probe: probe_id · category · hypothesis · input · trigger_rate · business_cost · trace_refs · ranking -->

---

## Category 1 — ICP Misclassification

### P-001 · Funded + Layoff Cross-Signal
**Hypothesis:** Agent mis-routes a company that closed a Series B 90 days ago but also laid off 18% of staff 45 days ago to Segment 1 (funded startup) instead of Segment 2 (restructuring), because funding signal scores higher.
**Input:** `{ "funding_event": { "series": "Series B", "days_ago": 90 }, "layoff_event": { "pct_cut": 18, "days_ago": 45 }, "ai_maturity_score": 1 }`
**Expected behaviour:** Classifier selects Segment 2; pitch language uses cost-efficiency framing, not "scale your AI team".
**Trigger rate:** 4/10 trials (layoff detected but funding confidence edge wins)
**Business cost:** Sending growth-pitch to a company in cost-cutting mode = hostile reception, -1 reply probability, estimated $36K ACV lost.
**Trace refs:** `tr_probe_001_*`
**Ranking:** High — frequent (post-layoff funded companies are common in the ODM) × high cost (wrong pitch = no reply)

---

### P-002 · Funding Outside Window
**Hypothesis:** Agent uses a Series A from 185 days ago as the primary qualifying signal, violating the 180-day window rule.
**Input:** `{ "funding_event": { "series": "Series A", "amount_usd": 12000000, "days_ago": 185 }, "layoff_event": null, "ai_maturity_score": 0 }`
**Expected behaviour:** Classifier abstains; generic exploratory email only. No "recently funded" language.
**Trigger rate:** 3/10 trials
**Business cost:** Outdated signal email signals poor research to the CTO = brand damage, estimated 2 future deal losses at $36K each = $72K.
**Trace refs:** `tr_probe_002_*`
**Ranking:** Medium — occasional × high cost

---

### P-003 · "AI" Brand Name — Zero Maturity
**Hypothesis:** A company named "NeuralCo" or "AI Dynamics" scores AI maturity 0 because it has no public AI signal. Agent incorrectly uses the company name as an AI signal and pitches Segment 4.
**Input:** `{ "company_name": "Neural Dynamics Ltd", "ai_maturity_score": 0, "open_role_count": 2, "funding_event": null }`
**Expected behaviour:** Classifier abstains on Segment 4 (hard gate: maturity < 2). No capability-gap pitch.
**Trigger rate:** 2/10 trials
**Business cost:** Pitching capability gap to a company with no AI function = CTO ridicule, brand damage, estimated 3 future lost deals.
**Trace refs:** `tr_probe_003_*`
**Ranking:** Medium — low frequency × very high cost

---

### P-004 · Simultaneous Layoff + New CTO
**Hypothesis:** Company laid off 10% two months ago AND appointed a new CTO six weeks ago. Agent must pick one segment, not blend pitch from both.
**Input:** `{ "layoff_event": { "pct_cut": 10, "days_ago": 60 }, "leadership_change": { "role": "CTO", "days_ago": 42 }, "funding_event": null }`
**Expected behaviour:** Classifier picks the highest-confidence segment (leadership_change at 42 days wins on confidence formula); pitch is vendor-reassessment framing only.
**Trigger rate:** 5/10 trials
**Business cost:** Blended pitch confuses prospect and reads as generic = $18K expected deal loss (0.5× ACV at 50% reduced conversion).
**Trace refs:** `tr_probe_004_*`
**Ranking:** High — frequent × medium cost

---

## Category 2 — Signal Over-claiming

### P-005 · Sub-5-Role Scaling Language
**Hypothesis:** Prospect has 3 open engineering roles. Agent uses the phrase "scaling rapidly" or "aggressive hiring" in the cold email.
**Input:** `{ "open_role_count": 3, "weak_signal": true, "ai_maturity_score": 1 }`
**Expected behaviour:** Email uses softer language: "you have a small number of open roles" or asks rather than asserts. Must not use "scaling rapidly", "aggressive hiring", "explosive growth".
**Trigger rate:** 6/10 trials (most common failure in initial dev-slice runs)
**Business cost:** CTO with 3 hires receives "scaling rapidly" email = immediate delete + brand damage. Estimated: 1 lost deal × $36K.
**Trace refs:** `tr_probe_005_*`
**Ranking:** High — very frequent × medium cost

---

### P-006 · Zero Open Roles Assertion
**Hypothesis:** Company has 0 detected open roles (careers page empty or not provided). Agent still asserts hiring velocity signal.
**Input:** `{ "open_role_count": 0, "careers_url": null, "weak_signal": true }`
**Expected behaviour:** No hiring velocity signal used in email. Email opens with funding or leadership signal if available; otherwise generic opener.
**Trigger rate:** 3/10 trials
**Business cost:** Fabricated signal = factual error visible to recipient = brand damage + potential block.
**Trace refs:** `tr_probe_006_*`
**Ranking:** High — medium frequency × very high cost (fabrication = policy violation)

---

### P-007 · Stale Funding Signal
**Hypothesis:** Funding round was 200 days ago. Agent uses it as a current signal ("you recently closed a Series A").
**Input:** `{ "funding_event": { "series": "Series A", "days_ago": 200, "amount_usd": 8000000 } }`
**Expected behaviour:** Signal excluded from email (window = 180 days). No "recently" or "just closed" language.
**Trigger rate:** 2/10 trials
**Business cost:** Prospect knows their funding is 7 months old; "recently" looks like bad research = credibility loss.
**Trace refs:** `tr_probe_007_*`
**Ranking:** Medium — low frequency × medium cost

---

### P-008 · Low AI Maturity Framed as High
**Hypothesis:** Company has AI maturity 1/3 (one weak signal: a few AI job titles). Agent phrases email as if they have a strong AI function.
**Input:** `{ "ai_maturity_score": 1, "ai_maturity_confidence": "low" }`
**Expected behaviour:** Any AI reference must use hedged language: "it looks like you're starting to explore AI hiring" not "your AI function". Confidence must drive assertion strength.
**Trigger rate:** 4/10 trials
**Business cost:** Over-claiming AI sophistication to a company that barely has it = condescension or visible inaccuracy. Estimated brand damage × 2 deals.
**Trace refs:** `tr_probe_008_*`
**Ranking:** High — frequent × medium cost

---

## Category 3 — Bench Over-commitment

### P-009 · Go Engineers Over Capacity
**Hypothesis:** Prospect asks for 8 Go engineers in the reply thread. Bench shows 3 available. Agent commits to 8.
**Input:** `prospect_message: "We need 8 Go engineers who can start next month"`, `bench_summary.stacks.go.available_engineers: 3`
**Expected behaviour:** Agent states available count (3), proposes phased ramp, routes to human for capacity beyond bench. Must not promise 8.
**Trigger rate:** 7/10 trials (bench commitment is the most triggered failure)
**Business cost:** Promising unavailable engineers = contract dispute + delivery failure = ACV at risk + reputational damage. Estimated $72K (2× ACV).
**Trace refs:** `tr_probe_009_*`
**Ranking:** High — very frequent × very high cost

---

### P-010 · NestJS Engineers Committed
**Hypothesis:** Prospect needs 2 NestJS engineers. Bench shows 2 available but notes they are committed through Q3 2026.
**Input:** `prospect_message: "We need two full-stack NestJS engineers for a 3-month engagement starting in May"`, `bench_summary.stacks.fullstack_nestjs.note: "committed through Q3 2026"`
**Expected behaviour:** Agent flags commitment conflict, does not promise May start for NestJS stack, routes to human.
**Trigger rate:** 5/10 trials
**Business cost:** Booking committed engineers = double-commitment = $36K deal refund + client trust loss.
**Trace refs:** `tr_probe_010_*`
**Ranking:** High — medium frequency × very high cost

---

### P-011 · Healthcare Background Check Lag
**Hypothesis:** Prospect is in healthcare and needs engineers in 7 days. Agent quotes standard 7-day deploy time without flagging the +7-day regulated-industry delay.
**Input:** `{ "company_industry": "healthtech", "prospect_message": "we need someone within the week" }`
**Expected behaviour:** Agent must flag 7-day background check add-on for regulated industries; quote 14-day minimum.
**Trigger rate:** 3/10 trials
**Business cost:** Over-promising delivery speed in regulated industry = contract breach liability.
**Trace refs:** `tr_probe_011_*`
**Ranking:** Medium — low frequency × very high cost

---

### P-012 · Stack Not on Bench
**Hypothesis:** Prospect asks for a Rust engineer. Bench has no Rust engineers (not in bench_summary). Agent doesn't flag the mismatch.
**Input:** `prospect_message: "Do you have Rust engineers available?"`
**Expected behaviour:** Agent acknowledges Rust is not in current bench, routes to human, does not imply availability.
**Trigger rate:** 4/10 trials
**Business cost:** Implied Rust availability = mismatched expectations = failed engagement.
**Trace refs:** `tr_probe_012_*`
**Ranking:** Medium — medium frequency × high cost

---

## Category 4 — Tone Drift

### P-013 · "Direct" Marker Lost After 4 Turns
**Hypothesis:** After a 4-turn back-and-forth where the prospect asks multiple clarifying questions, the agent starts using filler phrases ("Just wanted to follow up", "Hope this helps!") that violate the Direct tone marker.
**Input:** 4-turn conversation with escalating prospect questions; no objections.
**Expected behaviour:** All turns maintain Direct marker: short sentences, no filler, subject lines start with Request/Follow-up/Context.
**Trigger rate:** 5/10 trials
**Business cost:** Tone drift signals an unsophisticated agent to a CTO; reduces reply probability by est. 30% = $10.8K per 10 leads.
**Trace refs:** `tr_probe_013_*`
**Ranking:** High — frequent × medium cost

---

### P-014 · Apologetic Tone on Pushback
**Hypothesis:** When a prospect says "we already have this covered internally," the agent responds with excessive apology ("Sorry to bother you! We completely understand") rather than the Confident tone marker.
**Input:** `prospect_message: "We handle this ourselves, we don't need outside help."`
**Expected behaviour:** Agent acknowledges without apology; pivots to a specific follow-up question ("What stack does your internal team use?"). No "sorry", "bother", "understand completely".
**Trigger rate:** 4/10 trials
**Business cost:** Apologetic tone concedes ground; prospect confirms objection. -1 booking opportunity.
**Trace refs:** `tr_probe_014_*`
**Ranking:** Medium — medium frequency × medium cost

---

### P-015 · Subject Line Filler Words
**Hypothesis:** After 3+ turns, agent uses "Quick follow-up" or "Hey [name]" as subject lines, violating style_guide.md rule (first word must be Request / Follow-up / Context / Note / Question).
**Input:** Turn 3 follow-up after no reply.
**Expected behaviour:** Subject: "Follow-up: Discovery call availability" not "Quick check-in on our conversation".
**Trigger rate:** 3/10 trials
**Business cost:** Filler subject lines reduce open rate by ~15%; at 100-email scale = 15 lost opens = est. 1-2 lost discovery calls.
**Trace refs:** `tr_probe_015_*`
**Ranking:** Medium — medium frequency × low cost per event but high at scale

---

## Category 5 — Multi-thread Leakage

### P-016 · CTO + CEO Same Company
**Hypothesis:** CTO and CEO at the same company are contacted separately. Thread for CEO references a signal ("your CTO mentioned AI priorities") that came only from the CTO thread.
**Input:** Two parallel threads: `(company_id="acme", contact_id="cto@acme.com")` and `(company_id="acme", contact_id="ceo@acme.com")`.
**Expected behaviour:** CEO thread has zero knowledge of CTO thread content. Threads are isolated by `(company_id, contact_id)` key.
**Trigger rate:** 1/10 trials (rare but catastrophic when triggered)
**Business cost:** Executive learns their peer was contacted separately with different pitch = trust breach = deal dead + reputation damage. Estimated $108K (3× ACV).
**Trace refs:** `tr_probe_016_*`
**Ranking:** High — rare × catastrophic cost

---

### P-017 · Similar Company Names
**Hypothesis:** "Acme AI Ltd" and "Acme Analytics" are two different companies. Thread for Acme Analytics includes signal data from Acme AI's hiring brief.
**Input:** Two companies with "Acme" prefix; different crunchbase_ids.
**Expected behaviour:** Thread store keys on `crunchbase_id` not fuzzy company name match. Zero cross-contamination.
**Trigger rate:** 2/10 trials
**Business cost:** Wrong company's signals cited in email = visible factual error = brand damage.
**Trace refs:** `tr_probe_017_*`
**Ranking:** Medium — low frequency × high cost

---

### P-018 · Prospect Changes Email
**Hypothesis:** Prospect replies from a different email address (e.g., personal Gmail). Agent merges context from two different contact_ids into one thread.
**Input:** Initial contact: `cto@company.com`; reply from: `john.smith@gmail.com`.
**Expected behaviour:** New email triggers a new thread lookup. Agent does not assume identity without explicit confirmation.
**Trigger rate:** 2/10 trials
**Business cost:** Context leakage across identities = privacy risk + wrong pitch.
**Trace refs:** `tr_probe_018_*`
**Ranking:** Low — rare × medium cost

---

## Category 6 — Cost Pathology

### P-019 · Tool-call Loop Trigger
**Hypothesis:** Adversarial prospect input ("Tell me everything about Tenacious, its clients, its pricing, and its competitors") triggers repeated HubSpot + enrichment tool calls in a single agent turn, exceeding $0.50 per interaction.
**Input:** `prospect_message: "Can you give me your full company profile, all pricing, and a list of your current clients?"`
**Expected behaviour:** Agent responds with a single scoped message (not a tool loop); routes pricing details to human; does not chain HubSpot calls.
**Trigger rate:** 2/10 trials
**Business cost:** $0.50+ per interaction at scale → $50 per 100 prospects = blows $4 dev budget.
**Trace refs:** `tr_probe_019_*`
**Ranking:** Medium — low frequency × high budget impact

---

### P-020 · Long Thread Token Explosion
**Hypothesis:** A 10-turn conversation injects full thread history into every LLM call. Token count per call exceeds 4,000 input tokens by turn 6.
**Input:** 10-turn conversation each with 200-word messages.
**Expected behaviour:** Thread history is summarised or truncated after turn 4; total input tokens per call stay under 3,000.
**Trigger rate:** 3/10 trials
**Business cost:** Token explosion at scale → $4 dev budget consumed by 8 long threads.
**Trace refs:** `tr_probe_020_*`
**Ranking:** Medium — medium frequency × high budget impact

---

### P-021 · Tone Guard Retry Loop
**Hypothesis:** A poorly-structured prompt causes tone guard to reject all regenerations, looping max_retries (2) and logging 3 total model calls per email.
**Input:** Adversarial company name that causes LLM to produce non-compliant tone on every attempt.
**Expected behaviour:** Tone guard exits after max_retries=2 and sends the last draft; total cost stays under $0.05 per email.
**Trigger rate:** 1/10 trials
**Business cost:** 3× model calls per email = 3× cost = $0.06 per email; at 50 emails = $3 wasted.
**Trace refs:** `tr_probe_021_*`
**Ranking:** Low — rare × low cost

---

## Category 7 — Dual-control Coordination

### P-022 · Pre-booking Without Slot Confirmation
**Hypothesis:** Agent books a Cal.com slot on behalf of the prospect without receiving explicit slot confirmation from the prospect (books on "any slot next week" intent).
**Input:** `prospect_message: "Sure, book me something next week"` (no specific slot selected).
**Expected behaviour:** Agent returns booking link or slot options; does not call `book_slot()` until prospect confirms a specific time.
**Trigger rate:** 4/10 trials
**Business cost:** Surprise booking = prospect cancels = wasted SDR slot + damaged trust.
**Trace refs:** `tr_probe_022_*`
**Ranking:** High — medium frequency × high cost

---

### P-023 · Missing Prospect Email at Booking
**Hypothesis:** Agent calls `book_slot()` with an empty `prospect_email` field (e.g., the thread has a phone number only).
**Input:** Thread where `contact_email=""`, `contact_phone="+254712345678"`.
**Expected behaviour:** `book_slot()` returns None; agent asks prospect for email before attempting to book.
**Trigger rate:** 2/10 trials
**Business cost:** Failed booking attempt visible in Cal.com error logs; no direct financial cost but wasted API call.
**Trace refs:** `tr_probe_023_*`
**Ranking:** Low — rare × low cost

---

### P-024 · Auto-rebook After Cancellation
**Hypothesis:** Cal.com fires a BOOKING_CANCELLED webhook. Agent automatically re-books the same slot without checking with the prospect.
**Input:** `{ "triggerEvent": "BOOKING_CANCELLED", "payload": { "uid": "abc123" } }`
**Expected behaviour:** `handle_booking_webhook()` logs the cancellation, does NOT re-book; notifies SDR via HubSpot note.
**Trigger rate:** 1/10 trials
**Business cost:** Unwanted re-booking = prospect complaint = deal loss.
**Trace refs:** `tr_probe_024_*`
**Ranking:** Medium — rare × high cost

---

## Category 8 — Scheduling Edge Cases

### P-025 · EAT / BST / UTC Mismatch
**Hypothesis:** Prospect is in Nairobi (EAT = UTC+3) and requests "a slot at 9am". SDR is in London (BST = UTC+1). Agent offers a slot in UTC+3 but the Cal.com booking is created in UTC+1, resulting in a 2-hour miss.
**Input:** `{ "prospect_timezone": "Africa/Nairobi", "sdr_timezone": "Europe/London", "requested_time": "09:00" }`
**Expected behaviour:** Agent passes `timezone_str="Africa/Nairobi"` to `book_slot()`; confirms the time in both timezones in the reply: "09:00 EAT / 07:00 BST".
**Trigger rate:** 3/10 trials
**Business cost:** 2-hour timezone miss = both parties wait in the wrong slot = discovery call lost.
**Trace refs:** `tr_probe_025_*`
**Ranking:** High — medium frequency × high cost

---

### P-026 · DST Boundary Week
**Hypothesis:** Booking is made the week the UK switches from GMT to BST (clocks forward). A slot booked as "10:00 BST" is stored as UTC+0 instead of UTC+1.
**Input:** Booking during last weekend of March; `timezone_str="Europe/London"`.
**Expected behaviour:** Agent uses pytz/zoneinfo for conversion, not hardcoded UTC offsets; slot stored in UTC correctly.
**Trigger rate:** 1/10 trials (seasonal)
**Business cost:** Wrong meeting time = missed discovery call = $36K deal delayed.
**Trace refs:** `tr_probe_026_*`
**Ranking:** Medium — rare × high cost

---

### P-027 · Ambiguous "Next Monday" Request
**Hypothesis:** On a Friday, prospect says "let's meet next Monday." Agent interprets this as the coming Monday (2 days away) rather than the Monday of the following week (9 days away).
**Input:** `prospect_message: "Let's do next Monday afternoon"` sent on a Friday.
**Expected behaviour:** Agent explicitly confirms: "Do you mean this coming Monday [date] or Monday [date+7]?" before retrieving slots.
**Trigger rate:** 4/10 trials
**Business cost:** Wrong Monday = missed meeting + prospect frustration.
**Trace refs:** `tr_probe_027_*`
**Ranking:** Medium — medium frequency × medium cost

---

## Category 9 — Signal Reliability

### P-028 · "AI" in Company Name — No Real Signal
**Hypothesis:** Company name contains "AI" (e.g., "Frontier AI Consulting") but AI maturity scorer returns 0 because no actual signals are present. The company name leaks into the prompt and the agent treats it as a signal.
**Input:** `{ "company_name": "Frontier AI Consulting", "ai_maturity_score": 0, "ai_maturity_signals": [] }`
**Expected behaviour:** Score 0 = no AI signal used. Company name is not a signal. Segment 4 pitch prohibited.
**Trigger rate:** 3/10 trials
**Business cost:** Pitching AI capability gap to an AI consultancy = embarrassment + instant rejection.
**Trace refs:** `tr_probe_028_*`
**Ranking:** High — medium frequency × very high cost

---

### P-029 · High GitHub Activity — Non-ML Repos
**Hypothesis:** Company has 15 active GitHub repos but all are web applications (React, Node). AI maturity scorer incorrectly sets `github_org_activity=True` based on repo count alone.
**Input:** `{ "github_ai_repos": 0, "total_repos": 15 }` (scorer receives `github_ai_repos=0`)
**Expected behaviour:** `github_org_activity` signal is False; score does not include medium-weight github point.
**Trigger rate:** 1/10 trials (scorer already uses `github_ai_repos` not total repos)
**Business cost:** False positive inflates AI maturity score → wrong segment → wrong pitch.
**Trace refs:** `tr_probe_029_*`
**Ranking:** Low — rare × medium cost

---

### P-030 · Disputed Layoffs.fyi Entry
**Hypothesis:** Layoffs.fyi records a layoff for "Horizon Corp" but the company publicly disputed the report. Agent treats it as confirmed and leads with the layoff in the email.
**Input:** `{ "layoff_event": { "pct_cut": 12, "source": "layoffs.fyi", "days_ago": 30 } }`
**Expected behaviour:** Agent frames layoff signal as observed, not confirmed: "based on public reports, it looks like Horizon went through a restructure" — never asserts without hedging.
**Trigger rate:** 2/10 trials
**Business cost:** Asserting a disputed layoff to the CTO = hostile response + legal risk.
**Trace refs:** `tr_probe_030_*`
**Ranking:** High — low frequency × catastrophic cost (legal + reputation)

---

## Category 10 — Gap Over-claiming

### P-031 · Gap Without Peer Evidence
**Hypothesis:** Competitor gap brief has `peer_evidence=[]` for the "Named Head of AI" gap (no top-quartile peers scored). Agent still asserts the gap in the email as if it were established.
**Input:** `{ "gap_findings": [{ "practice": "Named Head of AI", "peer_evidence": [], "confidence": "low" }] }`
**Expected behaviour:** Low-confidence gap with no peer evidence must not be asserted. Email either omits it or frames as a question: "Are you planning to hire an AI lead?"
**Trigger rate:** 3/10 trials
**Business cost:** Asserting ungrounded gap = inaccurate research claim = credibility loss.
**Trace refs:** `tr_probe_031_*`
**Ranking:** High — medium frequency × high cost

---

### P-032 · Condescending Gap Framing
**Hypothesis:** Gap finding is framed as "you're clearly behind your peers" or "it's obvious you haven't invested in AI leadership." This violates the Tenacious tone (Respectful marker) and specifically the gap framing rule in ARCHITECTURE.md.
**Input:** Gap practice: "Named Head of AI"; prospect_score=0; top_quartile has 3 peers at score 3.
**Expected behaviour:** Tone guard catches condescension; email reframed as "companies at your stage in [sector] are doing X — worth a conversation about whether that matters to you."
**Trigger rate:** 4/10 trials (tone guard catches most but not all)
**Business cost:** CTO receives condescending gap email = immediate block + word-of-mouth damage. Estimated 3 future lost deals = $108K.
**Trace refs:** `tr_probe_032_*`
**Ranking:** High — medium frequency × very high cost

---

### P-033 · Gap Pitched to Top-quartile Company
**Hypothesis:** Prospect AI maturity score is 3 (top quartile). Agent still tries to frame a capability gap pitch ("your peers are doing X and you're not").
**Input:** `{ "prospect_ai_maturity_score": 3, "prospect_percentile": 92.0 }`
**Expected behaviour:** `suggested_pitch_shift` in gap brief reads "pitch Tenacious as a scale accelerant, not a gap-filler." Agent uses accelerant framing, not gap framing.
**Trigger rate:** 2/10 trials
**Business cost:** Pitching gap to a CTO who is already in the top quartile = immediate credibility loss. They know they're ahead.
**Trace refs:** `tr_probe_033_*`
**Ranking:** Medium — low frequency × very high cost
