#!/usr/bin/env bash
# Download the BIRD dev set (CC BY-SA 4.0, https://bird-bench.github.io) into data/raw/.
# The archive is third-party data: it is never committed (see .gitignore) and is
# unpacked into its own directory so nothing inside it runs as part of this repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW="$ROOT/data/raw"
URL="https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"
# Size and date of the archive used for the pre-registered runs (checked 2026-11-09).
EXPECTED_BYTES=346207293

mkdir -p "$RAW"
cd "$RAW"

if [ ! -f dev.zip ]; then
  curl -fL --retry 3 -o dev.zip "$URL"
fi

ACTUAL_BYTES=$(wc -c < dev.zip | tr -d ' ')
if [ "$ACTUAL_BYTES" != "$EXPECTED_BYTES" ]; then
  echo "dev.zip is $ACTUAL_BYTES bytes, expected $EXPECTED_BYTES; upstream changed or download is partial" >&2
  exit 1
fi

sha256sum dev.zip | tee dev.zip.sha256

mkdir -p bird_dev
unzip -q -o dev.zip -d bird_dev
# The dev archive nests the databases in a second zip.
DBZIP=$(find bird_dev -name 'dev_databases.zip' | head -n 1 || true)
if [ -n "$DBZIP" ]; then
  unzip -q -o "$DBZIP" -d "$(dirname "$DBZIP")"
fi

find bird_dev -name '*.sqlite' | sort
