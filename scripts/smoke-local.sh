#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:3000}"
CANDIDATE_URL="${CANDIDATE_URL:-http://localhost:3001}"
HR_URL="${HR_URL:-http://localhost:3002}"

for service in db api candidate-web hr-web; do
  if ! docker compose ps --services | grep -qx "$service"; then
    echo "missing compose service: $service" >&2
    exit 1
  fi
done

wait_for() {
  local url="$1"
  for _ in $(seq 1 40); do
    if curl -fsS --max-time 3 "$url" >/dev/null; then
      return 0
    fi
    sleep 3
  done
  echo "timed out waiting for $url" >&2
  return 1
}

wait_for "$API_URL/health"
wait_for "$CANDIDATE_URL/"
wait_for "$HR_URL/sign-in"

headers="$(mktemp)"
trap 'rm -f "$headers"' EXIT

curl -fsS -D "$headers" -o /dev/null -X POST "$HR_URL/api/auth/sign-in" \
  -H 'Content-Type: application/json' \
  -d '{"email":"hr@talotrace.ai","password":"change-me"}'
if ! grep -qi '^set-cookie: hr_access=' "$headers"; then
  echo "HR sign-in did not set the hr_access cookie" >&2
  exit 1
fi

curl -fsS -D "$headers" -o /dev/null -X OPTIONS "$API_URL/candidate/interview" \
  -H "Origin: $CANDIDATE_URL" \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-candidate-token'
if ! grep -qi "^access-control-allow-origin: $CANDIDATE_URL" "$headers"; then
  echo "CORS preflight did not allow $CANDIDATE_URL" >&2
  exit 1
fi

echo "local smoke ok"
