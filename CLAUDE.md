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

The five checks in `check.sh`, each runnable on its own:

1. `python3 -m py_compile firefighter_defense.py` — Python parses.
2. `python3 firefighter_defense.py --check-content` — fire facts match the reference (headless, no framework).
3. `python3 firefighter_defense.py --simulate` — the first level is winnable **only** by safe, correct play.
4. Node syntax-check of the embedded browser JS (skipped if Node absent).
5. `pytest -q` — the full test suite (`test_app.py`).

Run a single test: `pytest test_app.py::test_name -q` (or `-k pattern`).

The `--check-content` and `--simulate` modes exit without starting a server or importing FastAPI — this
is what CI and the pre-commit hook rely on, and what lets logic be tested in a framework-free sandbox.

## Checks run automatically — you cannot ship a broken change

- **Pre-commit hook** (`.githooks/pre-commit`) runs `check.sh` on every commit. Enable it once with
  `git config core.hooksPath .githooks`.
- **GitHub Actions** (`.github/workflows/checks.yml`) re-runs the exact same `check.sh` on every push/PR.
- `deploy.sh` uses `git add -u` only (tracked files) so scratch/transfer folders (`_to_delete/`, `_xfer/`)
  can never be committed by accident.

## Architecture

**The entire game is one file: `firefighter_defense.py`** (~3,700 lines). Understanding its layout matters
more than anything else here:

- **~60% of the file is one giant embedded string, `GAME_HTML`** (roughly lines 1477–3640) — the whole
  browser front-end (HTML + CSS + JavaScript) pasted into Python. The Python "logic" is actually small.
- **Python logic** is organized by clearly-commented section banners (`# --- ... ---`):
  - **Config** (env-overridable: `HOST`, `PORT`, `DATABASE_PATH`, `SCHEMA_VERSION`, `CONTENT_VERSION`).
  - **Fire facts** — `FIRE_CLASSES`, tool/cost tables. The machine-readable encoding of the safety reference.
  - **Text-as-data** — `L(de, en)` helper and the `anton_*` / `mission_lines_de` / `finale_de` narration
    functions. All player-facing strings pass through this so a language switch stays possible.
  - **Database** — `init_db`, `build_content`, `load_matrix`. SQLite, **rebuilt from source on every start**
    (see below). `check_content` compares the built content against the reference.
  - **Levels** — `LEVELS` data (map, path waypoints, build spots, waves) plus geometry helpers.
  - **`GameState`** (~line 844) — the single core game object holding all play/simulation logic.
  - **Checks** — `check_levels`, `check_narration`, and `behaviour_check` (the `--simulate` safe-play proof).
  - **Web app** — `render_game_html`, then `build_app()` which imports FastAPI *lazily* and defines the
    routes: `/`, `/health`, `/api/levels`, `/api/level/{i}`, `/api/classes`, `/api/tools`, `/api/anton`,
    `/api/matrix`.

**Data flow of the facts:** `FIRE_CLASSES` / content tables → `build_content` writes SQLite → `/api/matrix`
serves the class×tool→outcome grid → the browser resolves every shot against that grid. **The browser never
hard-codes fire facts** — it asks the API, which reads the DB, which was built from the reference.

**The database is disposable.** It builds itself on startup (`_lifespan` / `init_db`) from the app's own
content, so free hosting that wipes disk on restart is fine and `*.db` is gitignored. Never hand-edit the
`.db` file; edit the source content and let it rebuild.

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

## Known refactor direction

`firefighter_defense.py` is large mostly because the front-end is embedded as a string. The planned (not yet
done) refactor is to extract `GAME_HTML` into `templates/index.html` + `static/game.js` + `static/styles.css`,
then split the Python logic and tests into themed files — one small step at a time, on a branch, game running
and checks passing after each. See `../REFACTOR_PLAN_and_CLAUDE_CODE_GUIDE.md`.

## Sandbox note

In a no-internet sandbox, FastAPI may not install, so the full app can't boot. The game logic, content check,
and safe-play simulator all run **without** the framework (that's why `build_app` imports it lazily). When the
web layer can't be exercised, say so loudly on the board item — never treat a "couldn't test the web layer
here" gap as a pass.
