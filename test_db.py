"""Tests for the SQLite database — creation, schema, content loaded into it (db.py)

Split out of the old test_app.py (Step C)."""
import os

import firefighter_defense as g
from helpers import *  # shared test builders/play-drivers

def test_db_is_created(tmp_path):
    db = str(tmp_path / "test.db")
    assert not os.path.exists(db)
    g.init_db(db)
    assert os.path.exists(db), "the database file should exist after init"


def test_schema_version_recorded(tmp_path):
    db = str(tmp_path / "test.db")
    g.init_db(db)
    assert g.read_meta("schema_version", db) == str(g.SCHEMA_VERSION)


def test_init_is_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    g.init_db(db)
    g.init_db(db)  # calling again must not error or duplicate
    assert g.read_meta("schema_version", db) == str(g.SCHEMA_VERSION)


def test_db_rebuilds_after_deletion(tmp_path):
    db = str(tmp_path / "test.db")
    g.init_db(db)
    os.remove(db)
    assert not os.path.exists(db)
    g.init_db(db)
    assert os.path.exists(db), "deleting the database and restarting should recreate it"


def test_custom_database_path_is_used(tmp_path):
    nested = str(tmp_path / "sub" / "dir" / "game.db")
    g.init_db(nested)  # a fresh, non-existent folder should be created
    assert os.path.exists(nested)


# --- ITEM-006: the fire content and its guard check --------------------------

def test_content_loads(tmp_path):
    db = str(tmp_path / "c.db")
    g.init_db(db)
    nc, nt = g.content_counts(db)
    assert nc == len(g.FIRE_CLASSES)
    assert nt == len(g.TOOLS)


def test_matrix_is_complete(tmp_path):
    db = str(tmp_path / "c.db")
    g.init_db(db)
    m = g.load_matrix(db)
    assert len(m) == len(g.FIRE_CLASSES) * len(g.TOOLS)


def test_key_facts_match_reference(tmp_path):
    db = str(tmp_path / "c.db")
    g.init_db(db)
    m = g.load_matrix(db)
    assert m[("electrical", "water")] == "danger"   # never water on electrical
    assert m[("F", "water")] == "danger"            # never water on cooking oil
    assert m[("F", "wetchem")] == "good"            # the kitchen extinguisher
    assert m[("electrical", "co2")] == "good"
    assert m[("D", "metal")] == "good"


def test_every_class_has_a_correct_tool(tmp_path):
    db = str(tmp_path / "c.db")
    g.init_db(db)
    m = g.load_matrix(db)
    for c in g.FIRE_CLASSES:
        assert any(m[(c["id"], t["id"])] == "good" for t in g.TOOLS), \
            f"{c['id']} has no correct tool"
