# Working on Firefighter Defense — the development guide

This explains how to change the game safely: what the checks do, how they run by
themselves before every save, and how a change travels from an idea to something
shipped. It's written to be readable without a coding background.

## The one rule this setup enforces

**A change can't be saved into the history if it breaks the game's checks.** Every
time you save a change (a "commit"), the checks run first. If anything fails, the save
is stopped and you're told exactly what broke — so a bad change can't slip in by
accident.

## Turning the automatic checks on (do this once)

Open the Terminal, go into the game folder, and run this one line:

```
git config core.hooksPath .githooks
```

Expected: nothing is printed — it just returns to the prompt. That's success. From now
on, the checks run automatically every time you save a change.

(If you haven't set the game up as a git project yet, that happens in the "Put the game
on GitHub" step — see the deployment guide. Until then you can still run the checks by
hand, below.)

## Running all the checks yourself — one command

From inside the game folder:

```
./check.sh
```

Expected: it prints each check in turn (`1/5`, `2/5`, …) and ends with
`All checks finished.` If any check fails, it stops there and shows what went wrong,
and the command returns an error.

If you see `permission denied`, make it runnable once with:

```
chmod +x check.sh
```

## What each check is actually checking

1. **Does the code even parse?** — catches typos in the game code before anything else.
2. **Do the fire facts still match the reference?** — confirms the safety facts the game
   teaches (which extinguisher works on which fire, and which are dangerous) still match
   the source of truth. You can run just this one with:
   `python3 firefighter_defense.py --check-content`
3. **Is the first level still only won by playing safely?** — actually plays the first
   level to the end several ways and confirms: the right tool for each fire wins;
   doing nothing loses; an all-water defence loses; and ignoring the cooking-oil fires
   loses. If a change ever made the level winnable the wrong way, this fails. Run just
   this one with:  `python3 firefighter_defense.py --simulate`
4. **Does the on-screen (browser) code parse?** — the game draws itself in the browser;
   this catches typos in that part. It needs Node installed; if Node isn't there, this
   check is skipped with a note rather than failing.
5. **The full test suite** — the detailed checks. Needs `pytest`; install the extra
   dev tools once with:  `pip3 install -r requirements-dev.txt`

## Making a change, start to finish

1. **Make your edit.** Safety facts live in the fire reference and the game's content
   table, not scattered through the code — edit the source, and the game rebuilds its
   database from it on the next run.
2. **Run `./check.sh`** and confirm it ends with `All checks finished.`
3. **Save it** with a short note (a "commit"). The checks run again automatically and
   block the save if anything is broken.
4. **Don't hand-edit the generated database file** (`*.db`) — it's rebuilt every run and
   is deliberately not saved into the project.

## The safety rule

**Never change a fire fact just to make a check pass.** The fire reference is the
authority; the game bends to it. If the reference itself is genuinely wrong, fix it
there first, note what changed and why, and let everything rebuild from it.

## How this connects to the project board

- **Build** = making the change here, following the steps above.
- **Test** = running the checks and reporting, in plain terms, whether the change did
  what the board item asked for and left the checks passing.
- **Deploy** = pushing to GitHub (where the same checks run again automatically) and
  confirming the change is live on the hosted web address — see the deployment guide.

## A note for anyone building in a cloud sandbox

If the game is worked on in a cloud sandbox with no internet, the web framework
(FastAPI) may not install there, so the full app can't boot. The game is written so its
real logic — the database, the fire facts, the level play — runs and is checked
*without* the framework, and the web page itself is confirmed by opening the running app
on a real machine. A "couldn't test the web layer here" gap is flagged loudly on the
board item, never quietly treated as a pass.
