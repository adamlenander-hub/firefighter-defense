# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

This folder is the **code + git root** for Firefighter Defense — a cartoon tower-defense game that teaches
how to fight different classes of fire, built as the 150th-anniversary game for the *Freiwillige Feuerwehr
Königstein im Taunus*. Towers are extinguisher types; enemies are fires of different classes marching toward
a building. You win **only** by using the correct, safe extinguisher for each fire — a dangerous choice
(water on electrical or cooking-oil fires) backfires. Narrated by **Anton**, a water-shy castle ghost.
Player-facing language is **German**, with all text kept as data so an English version can be added later.

Live at https://firefighter-defense.onrender.com/ (hosted on Render via `render.yaml`).

Design, story, safety facts, and the work backlog live one level up in the project pack (`../docs/`,
`../backlog/`, `../process-notes.md`, `../REFACTOR_PLAN_and_CLAUDE_CODE_GUIDE.md`).

## Commands

Run from this folder:

```sh
pip3 install -r requirements.txt        # runtime deps (fastapi, uvicorn)
pip3 install -r requirements-dev.txt    # test deps (pytest, httpx)

python3 firefighter_defense.py          # run the game → http://localhost:3000

./check.sh                              # run ALL checks (see below); stops at first failure
./deploy.sh "note about what changed"   # stage tracked changes, commit (runs checks), push → Render redeploy
```

The six checks in `check.sh`, each runnable on its own:

1. `python3 -m py_compile firefighter_defense.py` — the entry point parses (steps 2-5 import the sibling modules, so those parse too).
2. `python3 firefighter_defense.py --check-content` — fire facts match the reference (headless, no framework).
3. `python3 firefighter_defense.py --simulate` — the first level is winnable **only** by safe, correct play.
4. `node --check static/game.js` — the browser code parses (skipped if Node absent).
5. `pytest -q` — the full test suite (the six `test_*.py` files).
6. `python3 browser_check.py` — plays the game in a **real headless browser**: confirms the browser's copy of the rules (`static/game.js`) still matches the Python engine (same matrix, same rule constants, same win/lose outcomes on the first level), and that the controls fit common phone screens. Skipped if Playwright absent; installed and enforced in CI. Add `--url https://…` to run the page/phone/health subset against the deployed site.

Run a single test: `pytest test_engine.py::test_name -q` (or `pytest -k pattern` to match by name across all files).

The `--check-content` and `--simulate` modes exit without starting a server or importing FastAPI — this
is what CI and the pre-commit hook rely on, and what lets logic be tested in a framework-free sandbox.

## Checks run automatically — you cannot ship a broken change

- **Pre-commit hook** (`.githooks/pre-commit`) runs `check.sh` on every commit. Enable it once with
  `git config core.hooksPath .githooks`.
- **GitHub Actions** (`.github/workflows/checks.yml`) re-runs the exact same `check.sh` on every push/PR.
- `deploy.sh` uses `git add -u` only (tracked files) so scratch/transfer folders (`_to_delete/`, `_xfer/`)
  can never be committed by accident.

## Architecture

The game is a **layered set of small Python modules** plus a separate browser front-end.
`firefighter_defense.py` is now a thin **entry point**: it re-exports every module
(`from config import *`, `from content import *`, ...) so `import firefighter_defense` still
exposes the same names the tests and CLI use, and it holds the `__main__` block (run the
server, `--check-content`, `--simulate`). Modules, in dependency order:

- **`config.py`** — all settings, each overridable by environment variable (`HOST`, `PORT`,
  `DATABASE_PATH`, `SCHEMA_VERSION`, `CONTENT_VERSION`). Depends on nothing.
- **`content.py`** — the fire facts and every line Anton speaks, as data (the machine-readable
  encoding of `../docs/FIRE_SAFETY_REFERENCE.md`, plus the `L(de, en)` text helper). Pure data;
  the rest of the app reads from here.
- **`db.py`** — the SQLite database: `init_db`, `build_content`, `load_matrix`. Rebuilt from
  `content.py` on every start.
- **`levels.py`** — `LEVELS` data (map, path waypoints, build spots, waves), the play-tuning
  constants, and the geometry/level helpers.
- **`engine.py`** — `GameState`, the framework-free, deterministic play engine. Runs and is
  tested without a browser.
- **`web.py`** — the FastAPI app: page assembly (`render_game_html`), the health check, and
  `build_app()`, which imports FastAPI **lazily** and defines the routes `/`, `/health`,
  `/api/levels`, `/api/level/{i}`, `/api/classes`, `/api/tools`, `/api/anton`, `/api/matrix`.
- **`checks.py`** — the "proof not claims" self-checks: `check_content`, `check_levels`,
  `check_narration`, and `behaviour_check` (the `--simulate` safe-play proof). Framework-free,
  so they run in CI and the pre-commit hook.

The browser front-end lives in its own files, served by the app rather than pasted into Python:
**`templates/index.html`** (the page), **`static/game.js`** (~1,850 lines of browser logic), and
**`static/styles.css`** (the look).

Tests mirror the modules — **`test_content.py`, `test_db.py`, `test_levels.py`, `test_engine.py`,
`test_web.py`, `test_checks.py`** — with shared builders/play-drivers in **`helpers.py`** and the
pytest setup (a FastAPI stand-in for offline runs) in **`conftest.py`**. Every test does
`import firefighter_defense as g` + `from helpers import *`. `sim_balance.py` is a non-shipped
tuning aid.

**Data flow of the facts:** `content.py` -> `build_content` writes SQLite -> `/api/matrix` serves the
class×tool->outcome grid -> the browser resolves every shot against that grid. **The browser never
hard-codes fire facts** — it asks the API, which reads the DB, which was built from the reference.

**The database is disposable.** It builds itself on startup (`_lifespan` / `init_db`) from
`content.py`, so free hosting that wipes disk on restart is fine and `*.db` is gitignored. Never
hand-edit the `.db` file; edit `content.py` (and the reference) and let it rebuild.

## The rules that make this project what it is

- **The game may never reward an unsafe choice.** Correct fire knowledge is how you win. `behaviour_check`
  (`--simulate`) enforces this on the first level: right tool wins, doing nothing loses, all-water loses,
  ignoring cooking-oil fires loses. If a change makes the level winnable the wrong way, this fails.
- **`../docs/FIRE_SAFETY_REFERENCE.md` is the single source of truth for fire facts.** Never change a fire
  fact just to make a check pass — the reference is the authority; the code bends to it. If the reference
  is genuinely wrong, fix it there first and let everything rebuild.
- **All player-facing text is German and lives as data** (via `L()` and the narration functions), not
  scattered string literals — this preserves the future English switch.

## Workflow (backlog → analyse → build → test → deploy)

Work is tracked as numbered items in `../backlog/` (`board.md` is the single source of truth for which stage
each item is in). Code comments frequently reference item numbers (e.g. `ITEM-016`, `ITEM-040`) explaining
*why* a mechanic exists. Every shipped item gets a retrospective logged in `../process-notes.md`.

## Refactor history

The layered layout above is the result of a refactor completed 2026-07-21 (git `890ba9a` ->
`cf5f4c6`): the embedded `GAME_HTML` string was extracted into `templates/` + `static/`, then the
Python logic and the old `test_app.py` were split into the themed modules and per-module test files
listed above — one small step at a time, on a branch, with the game running and every check passing
after each step. `../REFACTOR_PLAN_and_CLAUDE_CODE_GUIDE.md` is the plan that was followed (kept for reference).

## Sandbox note

In a no-internet sandbox, FastAPI may not install, so the full app can't boot. The game logic, content check,
and safe-play simulator all run **without** the framework (that's why `build_app` imports it lazily). When the
web layer can't be exercised, say so loudly on the board item — never treat a "couldn't test the web layer
here" gap as a pass.
