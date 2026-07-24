#!/bin/sh
# One command that runs every check for Firefighter Defense. Run it from this folder:
#     ./check.sh
# It stops at the first failure and returns an error code, so it can also be used by
# the pre-save hook and by the GitHub checks. Everything here needs no internet.

set -e

echo "1/6Reading the game code for typos (does it even parse?)"
python3 -m py_compile firefighter_defense.py
echo "     OK"

echo "2/6Checking the fire facts match the reference"
python3 firefighter_defense.py --check-content

echo "3/6Checking the first level is only won by safe, correct play"
python3 firefighter_defense.py --simulate

echo "4/6Checking the on-screen game code (the part that runs in the browser)"
if command -v node >/dev/null 2>&1; then
  # The browser code now lives in its own file (extracted from the Python), so it
  # can be syntax-checked directly — no need to pull it out of a Python string.
  node --check static/game.js
  echo "     OK"
else
  echo "     SKIPPED — Node isn't installed, so the browser code can't be syntax-checked here."
  echo "     (Install it from https://nodejs.org if you want this check to run.)"
fi

echo "5/6Running the full test suite"
if command -v pytest >/dev/null 2>&1; then
  pytest -q
elif python3 -c "import pytest" 2>/dev/null; then
  python3 -m pytest -q
else
  echo "     SKIPPED — pytest isn't installed."
  echo "     Install it with:  pip3 install -r requirements-dev.txt"
fi

echo "6/6  Playing the game in a real browser (rules match the server; fits phones)"
# This is the check that used to be done by hand: it opens the actual game in a
# headless browser, plays the first level to confirm the browser's copy of the rules
# still matches the Python engine (engine.py), and checks the buttons fit on common
# phone screens. It boots its own short-lived local server, so nothing needs to be
# running first. Needs Playwright + its browser; if those aren't installed it skips
# cleanly — the GitHub checks below install them, so it always runs there for real.
if python3 -c "import playwright" 2>/dev/null; then
  python3 browser_check.py
else
  echo "     SKIPPED — Playwright isn't installed, so the in-browser check can't run here."
  echo "     Enable it with:  pip3 install -r requirements-dev.txt  &&  python3 -m playwright install chromium"
fi

echo ""
echo "All checks finished."
