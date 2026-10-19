#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

src="intial-resources/business-systems-pack"
out="intial-resources/business-systems-pack.zip"

test -f "$src/questions.md"
test -f "$src/pipeline_log.csv"

rm -f "$out"
(cd "$src" && zip -qr "../../$out" questions.md pipeline_log.csv answers)
echo "$out"
