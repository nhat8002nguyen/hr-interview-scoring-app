#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

image_tag_override="${IMAGE_TAG:-}"
ghcr_owner_override="${GHCR_OWNER:-}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -n "$image_tag_override" ]]; then
  IMAGE_TAG="$image_tag_override"
fi
if [[ -n "$ghcr_owner_override" ]]; then
  GHCR_OWNER="$ghcr_owner_override"
fi

: "${IMAGE_TAG:?IMAGE_TAG required}"
: "${GHCR_OWNER:?GHCR_OWNER required}"
TBV_DEPLOY_DIR="${TBV_DEPLOY_DIR:-/opt/type-by-voice/deploy}"

docker compose pull
docker compose up -d --remove-orphans

health_ok=0
for _ in $(seq 1 30); do
  if docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/health', timeout=3)" >/dev/null 2>&1; then
    health_ok=1
    break
  fi
  sleep 3
done

if [[ "$health_ok" -ne 1 ]]; then
  echo "api health check failed after retries" >&2
  docker compose logs --tail=100 api >&2
  exit 1
fi

nginx_id="$(docker ps -q \
  -f "label=com.docker.compose.project=type-by-voice" \
  -f "label=com.docker.compose.service=nginx" | head -n 1)"
if [[ -z "$nginx_id" ]]; then
  echo "type-by-voice nginx container not found" >&2
  exit 1
fi

if ! docker inspect "$nginx_id" --format '{{json .NetworkSettings.Networks}}' | grep -q 'talot-edge'; then
  docker network connect talot-edge "$nginx_id"
fi

cp nginx/talot-api.conf "$TBV_DEPLOY_DIR/nginx/conf.d/talot-api.conf"

(
  cd "$TBV_DEPLOY_DIR"
  docker compose exec -T nginx nginx -t
  docker compose exec -T nginx nginx -s reload
)

echo "deploy ok: $IMAGE_TAG"
