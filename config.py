"""Configuration for Firefighter Defense — all overridable by environment variable."""
from __future__ import annotations

import os

# --- Configuration, all overridable by environment variable -------------------

HERE = os.path.dirname(os.path.abspath(__file__))

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "3000"))
# Default the database next to this script. No machine-specific paths are baked in,
# so the same code runs on a laptop or on a hosting server unchanged.
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(HERE, "firefighter_defense.db"))

# Bumped whenever the built-in content changes, so a later item (ITEM-006/039-style)
# can rebuild the database from the source of truth when this number moves.
SCHEMA_VERSION = 1

# Bumped whenever the fire content below changes, so the database rebuilds itself
# from this source on the next start (ITEM-006 / the "content version stamp" idea).
CONTENT_VERSION = 1

APP_TITLE = "Firefighter Defense — Königstein"
