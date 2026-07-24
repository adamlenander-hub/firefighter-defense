#!/bin/sh
# ship-verify.sh — the "is it REALLY done?" gate.
#
# WHO RUNS THIS: a fresh helper (or you) who did NOT build the change. Whoever built it
# does not get to sign off their own work — the same rule the project already uses for
# the tester-vs-builder split.
#
# WHEN: right before a card is allowed to move to "Done". Run it, then paste its output
# into the ticket. "Proof, not claims" — the ticket records what this actually printed,
# not a promise.
#
# WHAT IT CHECKS (the real state, not the ticket's word for it):
#   1. Your change is on the live branch — not stranded on a branch that never merged.
#      (This is the ITEM-060 failure: the work was "done" but on an unmerged branch.)
#   2. The full test suite actually passes right now, freshly run.
#      (This is the ITEM-058 failure: shipped while the suite was silently red.)
#   3. The live site is actually up — and, if a follow-up command is set, still behaves.
#
# RESULT: any FAIL or UNKNOWN means it is NOT done. UNKNOWN is not a pass — it means the
# check could not be run (missing config or no network), so the claim is unproven.
#
# CONFIG: reads ./ship-verify.conf if present (see the .conf next to this script), else
# environment variables, else the defaults below. Keys:
#   MAINLINE         the live branch the site ships from            (default: main)
#   CHECK_CMD        the one command that runs the full test suite  (e.g. "sh check.sh")
#   HEALTH_URL       a URL that returns 200 when the site is up     (e.g. .../health)
#   POST_DEPLOY_CMD  optional extra command to prove the LIVE site behaves
#                    (e.g. the browser test pointed at the deployed URL)
#
# Exit code: 0 only if every check PASSED. Non-zero if anything FAILED or is UNKNOWN.

# --- load config -------------------------------------------------------------
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$SCRIPT_DIR/ship-verify.conf" ]; then
  # shellcheck disable=SC1091
  . "$SCRIPT_DIR/ship-verify.conf"
fi
MAINLINE="${MAINLINE:-main}"

pass=0; fail=0; unknown=0
say()  { printf '%s\n' "$1"; }
ok()   { printf '  [ OK      ] %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  [ FAIL    ] %s\n' "$1"; fail=$((fail+1)); }
unk()  { printf '  [ UNKNOWN ] %s\n' "$1"; unknown=$((unknown+1)); }

say ""
say "  Completion gate — verifying real state (run by a fresh helper, not the builder)"
say "  ============================================================================"

# --- 1. on the live branch, nothing stranded --------------------------------
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  unk "On the live branch: this folder is not a git repository — can't check what shipped."
else
  cur=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  if [ "$cur" != "$MAINLINE" ]; then
    bad "On the live branch: you are on '$cur', but the site ships from '$MAINLINE'. Your work would not go live from here."
  elif [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    bad "On the live branch: you have uncommitted changes — they are NOT shipped. Commit or revert them first."
  else
    # Compare local mainline to the pushed one. Needs network; if we can't reach the
    # remote we say UNKNOWN rather than pretend it's in sync.
    if git fetch --quiet 2>/dev/null; then
      local_head=$(git rev-parse HEAD 2>/dev/null)
      remote_head=$(git rev-parse "origin/$MAINLINE" 2>/dev/null)
      if [ -z "$remote_head" ]; then
        unk "On the live branch: no 'origin/$MAINLINE' to compare against — is the remote set up?"
      elif [ "$local_head" = "$remote_head" ]; then
        ok "On the live branch '$MAINLINE', clean, and in sync with what's pushed ($(printf '%s' "$local_head" | cut -c1-9))."
      elif git merge-base --is-ancestor "$remote_head" HEAD 2>/dev/null; then
        bad "On the live branch: you have commits that are NOT pushed yet — the live site won't have them until you push."
      else
        bad "On the live branch: your local '$MAINLINE' is behind what's pushed — pull first; you may be verifying stale code."
      fi
    else
      unk "On the live branch '$MAINLINE', clean — but couldn't reach the remote to confirm it's pushed (no network?)."
    fi
  fi
fi

# --- 2. full suite actually green -------------------------------------------
if [ -z "$CHECK_CMD" ]; then
  unk "Full test suite: no CHECK_CMD is set, so the suite was not run. Set it in ship-verify.conf."
else
  say "  Running the full test suite:  $CHECK_CMD"
  if ( eval "$CHECK_CMD" ) >/tmp/ship_verify_tests.log 2>&1; then
    ok "Full test suite passes right now (freshly run)."
  else
    bad "Full test suite did NOT pass. Last lines:"
    tail -n 12 /tmp/ship_verify_tests.log | sed 's/^/           | /'
  fi
fi

# --- 3. actually deployed ----------------------------------------------------
if [ -z "$HEALTH_URL" ]; then
  unk "Live site: no HEALTH_URL is set, so the deploy was not checked. Set it in ship-verify.conf."
else
  code=$(curl -s -o /tmp/ship_verify_health.txt -w '%{http_code}' --max-time 20 "$HEALTH_URL" 2>/dev/null)
  if [ "$code" = "200" ]; then
    ok "Live site is up: $HEALTH_URL returned 200. Body: $(cat /tmp/ship_verify_health.txt 2>/dev/null | cut -c1-160)"
  elif [ -z "$code" ] || [ "$code" = "000" ]; then
    unk "Live site: couldn't reach $HEALTH_URL (no network, or the URL is wrong)."
  else
    bad "Live site: $HEALTH_URL returned HTTP $code, not 200 — the deploy may be down or not finished."
  fi
  if [ -n "$POST_DEPLOY_CMD" ]; then
    say "  Checking the live site behaves:  $POST_DEPLOY_CMD"
    if ( eval "$POST_DEPLOY_CMD" ) >/tmp/ship_verify_postdeploy.log 2>&1; then
      ok "Live site behaves (post-deploy check passed)."
    else
      bad "Live site post-deploy check FAILED. Last lines:"
      tail -n 12 /tmp/ship_verify_postdeploy.log | sed 's/^/           | /'
    fi
  fi
fi

# --- verdict -----------------------------------------------------------------
say "  ----------------------------------------------------------------------------"
if [ "$fail" -eq 0 ] && [ "$unknown" -eq 0 ]; then
  say "  DONE IS REAL — $pass checks passed. Safe to move the card to Done (paste this into the ticket)."
  say ""
  exit 0
else
  say "  NOT DONE — $pass passed, $fail failed, $unknown unknown."
  say "  A FAIL means it's broken; an UNKNOWN means it's unproven. Either way, do not mark it Done yet."
  say "  (Paste this into the ticket so the gap is recorded, not hidden.)"
  say ""
  exit 1
fi
