#!/bin/sh
# One-command deploy for Firefighter Defense.
#
# What it does, in order:
#   1. Checks you're on the live branch that the website ships from (main). If you're
#      on another branch, it does NOT quietly commit there and fail at the push
#      (which is how the ITEM-060 refactor nearly failed to ship). Instead it offers
#      to bring the live branch up to your current work and deploy from there — but
#      ONLY when that's a clean, no-conflict move; otherwise it stops and changes
#      nothing. See "Working on a side branch" below.
#   2. Stages every CHANGED file that git already tracks (plus this script itself).
#      It never stages brand-new or scratch files, so the _to_delete / _xfer transfer
#      folders the cloud session uses can't sneak into a commit.
#   3. Commits — which automatically runs the game's own checks through the pre-save
#      hook, so a change that breaks a check can't be shipped.
#   4. Pushes to GitHub, which makes Render rebuild and redeploy the live site.
#
# Run it from the firefighter-defense folder:
#     ./deploy.sh "a short note about what changed"
# If you leave the note out, it uses a dated default.
#
# Working on a side branch (not main):
#   - If your branch is simply ahead of main (main has nothing your branch is missing),
#     deploy asks first, then commits your work, moves main up to match, and pushes main.
#   - If main and your branch have BOTH moved on (they've diverged), deploy stops and
#     changes nothing — bring them together yourself, then re-run. It never makes a
#     commit that can't reach the live site.
#
# The push may ask for your GitHub username and your personal access token (the token
# goes in the password field — a plain password is rejected). To be asked only once,
# run this one-time setup first, then enter the token on your next push:
#     git config --global credential.helper osxkeychain

set -e
cd "$(dirname "$0")"

MSG="${1:-Update $(date '+%Y-%m-%d %H:%M')}"

# The branch the live site ships from (Render deploys origin/main).
LIVE_BRANCH="main"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# ---------------------------------------------------------------------------
# Guard: if you're not on the live branch, don't blindly commit + fail the push.
# ---------------------------------------------------------------------------
if [ "$CURRENT_BRANCH" != "$LIVE_BRANCH" ]; then
  # Is the live branch fully contained in your branch? If yes, moving it up to your
  # work is a clean fast-forward (no merge, no conflicts). If no, they've diverged.
  if ! git merge-base --is-ancestor "$LIVE_BRANCH" HEAD; then
    echo "You're on branch '$CURRENT_BRANCH', not the live branch '$LIVE_BRANCH'."
    echo "'$LIVE_BRANCH' has commits your branch doesn't, so this isn't a clean update."
    echo "Nothing was committed or pushed."
    echo "Bring them together yourself, for example:"
    echo "    git switch $LIVE_BRANCH && git merge $CURRENT_BRANCH"
    echo "then re-run ./deploy.sh from '$LIVE_BRANCH'."
    exit 1
  fi

  echo "You're on branch '$CURRENT_BRANCH', not the live branch '$LIVE_BRANCH'."
  echo "This will: commit your changes here, move '$LIVE_BRANCH' up to match, and deploy from '$LIVE_BRANCH'."
  printf "Proceed? [y/N] "
  read ANS || ANS=""
  case "$ANS" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Stopped. Nothing was committed or pushed."; exit 1 ;;
  esac

  # Commit your current changes on this branch (the pre-save hook runs the checks).
  git add -u
  git add deploy.sh 2>/dev/null || true
  if git diff --cached --quiet; then
    echo "No new file changes to commit — shipping the commits already on '$CURRENT_BRANCH'."
  else
    echo "About to deploy these changes:"
    git diff --cached --name-only | sed 's/^/  - /'
    echo "Commit message: $MSG"
    echo
    git commit -m "$MSG"
  fi

  # Move the live branch up to this branch's tip (a fast-forward, verified above) and push it.
  git branch -f "$LIVE_BRANCH" HEAD
  git push origin "$LIVE_BRANCH"

  echo
  echo "Deployed '$LIVE_BRANCH' (now matching '$CURRENT_BRANCH'). Render will rebuild in a few minutes."
  echo "The first visit after the site has been idle takes ~30s to wake — that's normal."
  exit 0
fi

# ---------------------------------------------------------------------------
# Normal path: you're on the live branch. Behaves exactly as before.
# ---------------------------------------------------------------------------

# Stage changes to already-tracked files, plus this script (so its first run ships it).
git add -u
git add deploy.sh 2>/dev/null || true

if git diff --cached --quiet; then
  echo "Nothing to deploy — no tracked files have changed."
  exit 0
fi

echo "About to deploy these changes:"
git diff --cached --name-only | sed 's/^/  - /'
echo "Commit message: $MSG"
echo

# The commit runs the game's checks first (pre-save hook); if any check fails the
# commit is stopped and nothing is pushed.
git commit -m "$MSG"
git push

echo
echo "Pushed to GitHub. Render will rebuild in a few minutes."
echo "The first visit after the site has been idle takes ~30s to wake — that's normal."
