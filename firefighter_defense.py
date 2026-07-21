"""
Firefighter Defense — Königstein 150-year anniversary edition ("Anton der Burggeist").

A single self-contained Python web app that
  * serves one page confirming the game is running (ITEM-005),
  * creates its own SQLite database next to itself on first run (ITEM-005), and
  * loads the fire facts — classes, tools, and the right/useless/dangerous matrix —
    from the source of truth below into that database, with a check that guards them
    against the fire-safety reference (ITEM-006).

It does NOT yet contain the levels or the playable game — those are later backlog
items. The shape every later item relies on: one FastAPI app, SQLite built on
startup from a source of truth, everything configurable by environment variable,
nothing tied to one specific computer, deployable unchanged.

Run it:
    pip install -r requirements.txt
    python3 firefighter_defense.py
Then open the address it prints (default http://localhost:3000).

Check the fire facts are correct (no server needed):
    python3 firefighter_defense.py --check-content

Check the first level is only won by safe, correct play (no server needed):
    python3 firefighter_defense.py --simulate

Configuration (all optional, read from the environment):
    HOST           network address to bind      (default 0.0.0.0 = reachable on the LAN)
    PORT           port to serve on             (default 3000; hosting providers set this)
    DATABASE_PATH  where the SQLite file lives   (default: next to this script)
"""
from __future__ import annotations

# The code now lives in themed sibling modules; this file stays the entry point
# and the public surface. Re-export everything so `import firefighter_defense`
# still exposes the same names (the test suite and the CLI below rely on it).
from config import *
from content import *
from db import *
from levels import *
from engine import *
from checks import *
from web import *
from checks import _play_out  # underscored, so not pulled in by `import *`


# --- Run ---------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # `--check-content` runs the fire-facts check and exits — no server, no web
    # framework needed. This is what the automatic checks (CI) and the pre-save
    # hook call.
    if "--check-content" in sys.argv:
        init_db()
        ok1, p1 = check_content()
        ok2, p2 = check_levels()
        ok3, p3 = check_narration()          # ITEM-026: guard Anton's mission hints (DE + EN)
        ok4, p4 = check_english_content()    # German→English switch: English is complete + safe
        if ok1 and ok2 and ok3 and ok4:
            nc, nt = content_counts()
            print(f"Checks PASSED — {nc} Brandklassen, {nt} Löschmittel, "
                  f"{level_count()} Level, {len(campaign_missions())} Story-Missionen, "
                  f"Antons Hinweise (DE+EN) geprüft, englische Inhalte vollständig, "
                  f"alle Prüfungen bestanden.")
            sys.exit(0)
        print("Checks FAILED:")
        for p in p1 + p2 + p3 + p4:
            print("  -", p)
        sys.exit(1)

    # `--simulate` plays the first level to the end with several strategies and
    # confirms only safe, correct play wins. Exits 0 if the game still teaches, 1 if
    # a change has made it winnable the wrong way. No server, no web request needed.
    if "--simulate" in sys.argv:
        ok, problems = behaviour_check()
        if ok:
            print("Behaviour check PASSED — the first level is only won by safe, correct play.")
            sys.exit(0)
        print("Behaviour check FAILED:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    import uvicorn

    # Build the database before we start serving, so the very first request works
    # even if the startup event hasn't run yet in some setups.
    init_db()
    app = build_app()
    print(f"Firefighter Defense läuft auf  http://{HOST}:{PORT}")
    print(f"Datenbank: {DATABASE_PATH}")
    uvicorn.run(app, host=HOST, port=PORT)
