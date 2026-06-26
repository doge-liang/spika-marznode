"""Schema self-heal: _add_column_if_missing applies an additive column on
every boot regardless of user_version, and is idempotent."""
import sqlite3

from marznode.storage.sqlite import SqliteStorage, _add_column_if_missing


def test_add_column_if_missing_adds_then_noop(tmp_path):
    db = str(tmp_path / "t.db")
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        assert _add_column_if_missing(c, "users", "note", "TEXT") is True
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
        assert "note" in cols
        # second call is a no-op, no error
        assert _add_column_if_missing(c, "users", "note", "TEXT") is False


def test_init_schema_stamps_user_version(tmp_path):
    db = str(tmp_path / "marznode.db")
    SqliteStorage(db_path=db)  # __init__ calls _init_schema
    with sqlite3.connect(db) as c:
        version = c.execute("PRAGMA user_version").fetchone()[0]
    from marznode.storage.sqlite import _SCHEMA_VERSION
    assert version == _SCHEMA_VERSION
