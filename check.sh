#!/bin/sh
# One command that runs every check for Firefighter Defense. Run it from this folder:
#     ./check.sh
# It stops at the first failure and returns an error code, so it can also be used by
# the pre-save hook and by the GitHub checks. Everything here needs no internet.

set -e

echo "1/5  Reading the game code for typos (does it even parse?)"
python3 -m py_compile firefighter_defense.py
echo "     OK"

echo "2/5  Checking the fire facts match the reference"
python3 firefighter_defense.py --check-content

echo "3/5  Checking the first level is only won by safe, correct play"
python3 firefighter_defense.py --simulate

echo "4/5  Checking the on-screen game code (the part that runs in the browser)"
if command -v node >/dev/null 2>&1; then
  python3 - <<'PY'
import re
src = open("firefighter_defense.py", encoding="utf-8").read()
m = re.search(r'GAME_HTML\s*=\s*[a-z]*"""(.*?)"""', src, re.S)
html = m.group(1) if m else ""
js = "".join(re.findall(r"<script>(.*?)</script>", html, re.S))
open(".game.check.js", "w", encoding="utf-8").write(js)
PY
  node --check .game.check.js
  rm -f .game.check.js
  echo "     OK"
else
  echo "     SKIPPED — Node isn't installed, so the browser code can't be syntax-checked here."
  echo "     (Install it from https://nodejs.org if you want this check to run.)"
fi

echo "5/5  Running the full test suite"
if command -v pytest >/dev/null 2>&1; then
  pytest -q
elif python3 -c "import pytest" 2>/dev/null; then
  python3 -m pytest -q
else
  echo "     SKIPPED — pytest isn't installed."
  echo "     Install it with:  pip3 install -r requirements-dev.txt"
fi

echo ""
echo "All checks finished."
