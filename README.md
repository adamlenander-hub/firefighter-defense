# Firefighter Defense — Feuerwehr Königstein

A small, cartoonish **tower-defense game that teaches the right way to fight different
kinds of fire.** Towers are extinguisher types; the enemies are fires of different
classes marching toward a building. You win only by using the *correct, safe*
extinguisher for each fire — using a dangerous one (like water on an electrical or a
cooking-oil fire) backfires.

Built as the 150-year anniversary game for the **Freiwillige Feuerwehr Königstein im
Taunus**, narrated by **Anton**, a water-shy castle ghost. The game is in German, with
all player-facing text kept as data so an English version can be added later.

It's a single self-contained Python app: one file plus a couple of standard web
libraries. It builds its own database of fire facts on startup, so there's nothing to
set up and nothing that needs to survive a restart.

## Play it locally

You need Python 3 (3.10 or newer). From this folder:

    pip3 install -r requirements.txt
    python3 firefighter_defense.py

Then open the address it prints (by default http://localhost:3000).

## Run the checks

    ./check.sh

This confirms the code parses, the fire facts match the safety reference, the first
level is only won by safe play, the browser code parses, and the test suite passes.
See **DEVELOPMENT.md** for what each check means and how the automatic pre-save check
works.

## How it's hosted

The game deploys as one package to [Render](https://render.com) using the included
`render.yaml` blueprint — a single free web service, no database add-on needed (the
game rebuilds its content on startup). The same checks run automatically on GitHub on
every change (`.github/workflows/checks.yml`).

## Safety facts come from a reference, not guesswork

The extinguisher-vs-fire facts the game teaches are checked against a written
fire-safety reference on every run. The rule is: never change a fact to make a check
pass — the reference is the authority.
