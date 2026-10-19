#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${DOMAIN:?DOMAIN required}"
: "${CERTBOT_EMAIL:?CERTBOT_EMAIL required}"
TBV_DEPLOY_DIR="${TBV_DEPLOY_DIR:-/opt/type-by-voice/deploy}"

docker network inspect talot-edge >/dev/null 2>&1 || docker network create talot-edge

if [[ -f "$TBV_DEPLOY_DIR/docker-compose.override.yml" ]]; then
  if ! grep -q 'talot-edge' "$TBV_DEPLOY_DIR/docker-compose.override.yml"; then
    echo "existing $TBV_DEPLOY_DIR/docker-compose.override.yml does not reference talot-edge" >&2
    exit 1
  fi
else
  cp nginx/talot-edge.override.yml "$TBV_DEPLOY_DIR/docker-compose.override.yml"
fi

cp nginx/talot-api.http-bootstrap.conf "$TBV_DEPLOY_DIR/nginx/conf.d/talot-api.conf"

(
  cd "$TBV_DEPLOY_DIR"
  docker compose up -d --no-deps nginx
  docker compose exec -T nginx nginx -t
  docker compose exec -T nginx nginx -s reload
  docker compose run --rm --no-deps --entrypoint "" certbot \
    certbot certonly \
    --webroot -w /var/www/certbot \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    --domains "$DOMAIN"
)

echo "certificate issued for $DOMAIN; run deploy.sh to install the TLS site"
