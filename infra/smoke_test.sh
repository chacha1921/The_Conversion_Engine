#!/usr/bin/env bash
# Smoke test — verifies all five stack components are reachable.
# Run from repo root: bash infra/smoke_test.sh
# Expected: five green checks. Any red X = not ready for Day 1 review.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

GREEN="\033[0;32m"
RED="\033[0;31m"
RESET="\033[0m"

pass() { echo -e "${GREEN}✓ $1${RESET}"; }
fail() { echo -e "${RED}✗ $1${RESET}"; FAILED=1; }

FAILED=0

# Load .env
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

echo ""
echo "=== Conversion Engine Smoke Test ==="
echo ""

# ── 1. Email (Resend) ──────────────────────────────────────────────────
if [ -z "${RESEND_API_KEY:-}" ]; then
  fail "Email — RESEND_API_KEY not set"
else
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -X GET "https://api.resend.com/emails" \
    -H "Authorization: Bearer ${RESEND_API_KEY}" \
    --max-time 10)
  # Resend returns 200 on valid key, 401 on invalid
  if [ "$HTTP" = "200" ] || [ "$HTTP" = "405" ]; then
    pass "Email (Resend) — API key valid"
  else
    fail "Email (Resend) — API returned HTTP $HTTP (check RESEND_API_KEY)"
  fi
fi

# ── 2. SMS (Africa's Talking) ──────────────────────────────────────────
if [ -z "${AT_API_KEY:-}" ]; then
  fail "SMS — AT_API_KEY not set"
else
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -X GET "https://api.sandbox.africastalking.com/version1/user?username=${AT_USERNAME:-sandbox}" \
    -H "apiKey: ${AT_API_KEY}" \
    -H "Accept: application/json" \
    --max-time 10)
  if [ "$HTTP" = "200" ]; then
    pass "SMS (Africa's Talking sandbox) — API key valid"
  else
    fail "SMS (Africa's Talking) — API returned HTTP $HTTP (check AT_API_KEY)"
  fi
fi

# ── 3. HubSpot ────────────────────────────────────────────────────────
if [ -z "${HUBSPOT_ACCESS_TOKEN:-}" ]; then
  fail "HubSpot — HUBSPOT_ACCESS_TOKEN not set"
else
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -X GET "https://api.hubapi.com/crm/v3/objects/contacts?limit=1" \
    -H "Authorization: Bearer ${HUBSPOT_ACCESS_TOKEN}" \
    --max-time 10)
  if [ "$HTTP" = "200" ]; then
    pass "HubSpot — API token valid, CRM reachable"
  else
    fail "HubSpot — API returned HTTP $HTTP (check HUBSPOT_ACCESS_TOKEN)"
  fi
fi

# ── 4. Cal.com ────────────────────────────────────────────────────────
CALCOM_URL="${CALCOM_BASE_URL:-http://localhost:3000}"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  "$CALCOM_URL" \
  --max-time 10 2>/dev/null || echo "000")
if [ "$HTTP" = "200" ] || [ "$HTTP" = "302" ] || [ "$HTTP" = "307" ]; then
  pass "Cal.com — reachable at $CALCOM_URL"
else
  fail "Cal.com — not reachable at $CALCOM_URL (HTTP $HTTP) — is Docker running?"
fi

# ── 5. Langfuse ───────────────────────────────────────────────────────
if [ -z "${LANGFUSE_PUBLIC_KEY:-}" ] || [ -z "${LANGFUSE_SECRET_KEY:-}" ]; then
  fail "Langfuse — LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set"
else
  LANGFUSE_HOST="${LANGFUSE_HOST:-https://cloud.langfuse.com}"
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -X GET "$LANGFUSE_HOST/api/public/projects" \
    -u "${LANGFUSE_PUBLIC_KEY}:${LANGFUSE_SECRET_KEY}" \
    --max-time 10)
  if [ "$HTTP" = "200" ]; then
    pass "Langfuse — API keys valid, project reachable"
  else
    fail "Langfuse — API returned HTTP $HTTP (check LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY)"
  fi
fi

# ── Kill-switch guard ─────────────────────────────────────────────────
echo ""
if grep -q "^TENACIOUS_OUTBOUND_ENABLED=true" "$ENV_FILE" 2>/dev/null; then
  fail "Kill-switch — TENACIOUS_OUTBOUND_ENABLED=true is SET (must be unset for challenge week)"
else
  pass "Kill-switch — TENACIOUS_OUTBOUND_ENABLED is unset (safe)"
fi

# ── Policy acknowledgement ────────────────────────────────────────────
if [ -f "$REPO_ROOT/policy/acknowledgement_signed.txt" ]; then
  pass "Policy — acknowledgement_signed.txt present"
else
  fail "Policy — policy/acknowledgement_signed.txt missing"
fi

echo ""
if [ "$FAILED" -eq 0 ]; then
  echo -e "${GREEN}All checks passed. Ready for Day 1 review.${RESET}"
else
  echo -e "${RED}One or more checks failed. Fix above items before Day 1 review.${RESET}"
  exit 1
fi
