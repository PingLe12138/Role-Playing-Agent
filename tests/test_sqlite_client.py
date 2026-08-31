import os
import tempfile

import pytest

from SQLiteClient import SQLiteClient


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    c = SQLiteClient(os.path.basename(path), db_dir=os.path.dirname(path))
    c.execute("CREATE TABLE test_tx (id INTEGER PRIMARY KEY, val TEXT)")
    yield c
    c.close()
    try:
        os.unlink(path)
    except PermissionError:
        pass


class TestCRUD:
    def test_insert_and_fetch(self, client):
        client.execute("INSERT INTO test_tx (id, val) VALUES (1, 'hello')")
        row = client.fetchone("SELECT * FROM test_tx WHERE id = 1")
        assert row == {"id": 1, "val": "hello"}

    def test_fetchall(self, client):
        client.execute("INSERT INTO test_tx (id, val) VALUES (1, 'a')")
        client.execute("INSERT INTO test_tx (id, val) VALUES (2, 'b')")
        rows = client.fetchall("SELECT * FROM test_tx ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["val"] == "a"
        assert rows[1]["val"] == "b"

    def test_insert_twice_duplicate_raises(self, client):
        client.execute("INSERT INTO test_tx (id, val) VALUES (1, 'a')")
        with pytest.raises(Exception):
            client.execute("INSERT INTO test_tx (id, val) VALUES (1, 'b')")


class TestTransaction:
    def test_commit_persists(self, client):
        client.begin()
        client.execute("INSERT INTO test_tx (id, val) VALUES (1, 'persist')")
        client.commit()
        row = client.fetchone("SELECT val FROM test_tx WHERE id = 1")
        assert row["val"] == "persist"

    def test_rollback_discards(self, client):
        client.execute("INSERT INTO test_tx (id, val) VALUES (99, 'before_tx')")
        client.begin()
        client.execute("INSERT INTO test_tx (id, val) VALUES (1, 'will_rollback')")
        client.rollback()
        rows = client.fetchall("SELECT * FROM test_tx")
        assert len(rows) == 1
        assert rows[0]["id"] == 99

    def test_rollback_then_continue(self, client):
        client.begin()
        client.execute("INSERT INTO test_tx (id, val) VALUES (1, 'a')")
        client.rollback()

        client.begin()
        client.execute("INSERT INTO test_tx (id, val) VALUES (2, 'b')")
        client.commit()

        rows = client.fetchall("SELECT * FROM test_tx ORDER BY id")
        assert len(rows) == 1
        assert rows[0]["id"] == 2

    def test_auto_commit_outside_tx(self, client):
        client.execute("INSERT INTO test_tx (id, val) VALUES (1, 'auto')")
        client.begin()
        client.execute("INSERT INTO test_tx (id, val) VALUES (2, 'in_tx')")
        client.rollback()
        rows = client.fetchall("SELECT * FROM test_tx ORDER BY id")
        assert len(rows) == 1
        assert rows[0]["val"] == "auto"

    def test_close_rollback_open_tx(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        c = SQLiteClient(os.path.basename(path), db_dir=os.path.dirname(path))
        c.execute("CREATE TABLE test_tx (id INTEGER PRIMARY KEY, val TEXT)")
        c.begin()
        c.execute("INSERT INTO test_tx (id, val) VALUES (1, 'lost')")
        c.close()

        c2 = SQLiteClient(os.path.basename(path), db_dir=os.path.dirname(path))
        rows = c2.fetchall("SELECT * FROM test_tx")
        assert len(rows) == 0
        c2.close()
        os.unlink(path)
