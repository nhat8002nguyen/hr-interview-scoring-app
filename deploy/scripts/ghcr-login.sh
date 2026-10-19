#!/usr/bin/env bash
set -euo pipefail
echo "${GHCR_TOKEN:?GHCR_TOKEN required}" | docker login ghcr.io \
  -u "${GHCR_USER:?GHCR_USER required}" --password-stdin
