"""Regression tests for `clear_all`'s FK-pragma handling.

/ `clear_all` 外键 PRAGMA 处理的回归测试。

Background: `PRAGMA foreign_keys` is per-connection and `routers.deps.db` is the
shared process-wide connection. The old code turned enforcement ON after wiping the
tables, which leaked into later requests and made `POST /api/sessions` fail with
`FOREIGN KEY constraint failed` (the user character's relationship / emotion rows
reference `character_info_card`, but user characters live in another table).
/ 背景：外键开关是连接级的，而 routers.deps.db 是进程内共享连接。旧代码清空后把校验
  打开，泄漏到后续请求，导致建会话报 FOREIGN KEY constraint failed。
"""

import os
import tempfile

import pytest

from routers.misc import _delete_all_rows
from SQLiteClient import SQLiteClient

TABLES = ["child", "parent"]


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    c = SQLiteClient(os.path.basename(path), db_dir=os.path.dirname(path))
    c.execute("CREATE TABLE parent (id TEXT PRIMARY KEY)")
    c.execute("CREATE TABLE child (id TEXT PRIMARY KEY, pid TEXT, FOREIGN KEY (pid) REFERENCES parent(id))")
    c.execute("INSERT INTO parent (id) VALUES ('p1')")
    c.execute("INSERT INTO child (id, pid) VALUES ('c1', 'p1')")
    yield c
    c.close()
    try:
        os.unlink(path)
    except PermissionError:
        pass


def _fk_enabled(c) -> bool:
    return bool((c.fetchone("PRAGMA foreign_keys") or {}).get("foreign_keys", 0))


class TestDeleteAllRows:
    def test_wipes_every_table(self, client):
        _delete_all_rows(client, TABLES)
        assert client.fetchall("SELECT * FROM parent") == []
        assert client.fetchall("SELECT * FROM child") == []

    def test_keeps_fk_off_when_it_was_off(self, client):
        # sqlite3 default: enforcement off / sqlite3 默认关闭外键校验
        assert _fk_enabled(client) is False
        _delete_all_rows(client, TABLES)
        assert _fk_enabled(client) is False

    def test_keeps_fk_on_when_it_was_on(self, client):
        client.execute("PRAGMA foreign_keys = ON")
        _delete_all_rows(client, TABLES)
        assert _fk_enabled(client) is True

    def test_fk_restored_even_if_delete_fails(self, client):
        with pytest.raises(Exception):
            _delete_all_rows(client, ["no_such_table"])
        assert _fk_enabled(client) is False
