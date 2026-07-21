#!/bin/sh
# One-command deploy for Firefighter Defense.
#
# What it does, in order:
#   1. Stages every CHANGED file that git already tracks (plus this script itself).
#      It never stages brand-new or scratch files, so the _to_delete / _xfer transfer
#      folders the cloud session uses can't sneak into a commit.
#   2. Commits — which automatically runs the game's own checks through the pre-save
#      hook, so a change that breaks a check can't be shipped.
#   3. Pushes to GitHub, which makes Render rebuild and redeploy the live site.
#
# Run it from the firefighter-defense folder:
#     ./deploy.sh "a short note about what changed"
# If you leave the note out, it uses a dated default.
#
# The push may ask for your GitHub username and your personal access token (the token
# goes in the password field — a plain password is rejected). To be asked only once,
# run this one-time setup first, then enter the token on your next push:
#     git config --global credential.helper osxkeychain

set -e
cd "$(dirname "$0")"

MSG="${1:-Update $(date '+%Y-%m-%d %H:%M')}"

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
