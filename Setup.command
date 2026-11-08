#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ "$(uname -s)" != Darwin ]; then
  echo 'Score Player requires macOS for Apple Vision OCR.'
  exit 1
fi
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
clang -fobjc-arc -framework Foundation -framework Vision -framework CoreGraphics engines/tab-ocr.m -o engines/tab-ocr
clang -fobjc-arc -framework Foundation -framework Vision -framework CoreGraphics -framework ImageIO engines/fret-ocr.m -o engines/fret-ocr
mkdir -p data
echo 'Ready. Open Start Score Player.command.'
echo 'For staff notation, install Audiveris.app in engines. See README.md.'
