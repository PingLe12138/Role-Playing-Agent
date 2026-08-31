import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Union

import paths

_db_instance = None

# Serializes access to the shared sqlite3 connection across threads.
# Parallel graph nodes (e.g. the review chain fan-out) hold this lock around
# their DB write sections so that one node's open transaction cannot swallow
# another node's autocommit statements (which would be rolled back together).
# / 跨线程串行化对共享 sqlite3 连接的访问。并行图节点（如审查链扇出）在
#   DB 写段持有此锁，避免某节点打开的事务吞掉另一节点的自动提交语句
#   （连带回滚）。
db_lock = threading.Lock()


def get_db(db_name: str = "rpa_data.db", db_dir: Optional[str] = None) -> "SQLiteClient":
    global _db_instance
    if _db_instance is None:
        _db_instance = SQLiteClient(db_name, db_dir)
    return _db_instance


class SQLiteClient:
    """独立的 SQLite 数据库客户端"""

    def __init__(self, db_name: str, db_dir: Optional[str] = None):
        """
        :param db_name: 数据库文件名（如 "myapp.db"）
        :param db_dir: 数据库文件存放目录；缺省锚定项目根 data/（显式传入的相对/绝对路径原样生效）
        """
        self.db_name = db_name
        self.db_dir = db_dir if db_dir is not None else str(paths.DATA_DIR)
        self.db_path = os.path.join(self.db_dir, db_name)
        self._conn: Optional[sqlite3.Connection] = None
        self._in_transaction: bool = False

    def connect(self) -> sqlite3.Connection:
        """获取数据库连接（自动创建目录和连接）"""
        if self._conn is not None:
            return self._conn
        os.makedirs(self.db_dir, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        return self._conn

    def begin(self):
        """开启显式事务，后续 execute 不会自动 commit"""
        conn = self.connect()
        conn.execute("BEGIN")
        self._in_transaction = True

    def commit(self):
        """提交当前事务"""
        if self._in_transaction:
            self._conn.commit()
            self._in_transaction = False

    def rollback(self):
        """回滚当前事务"""
        if self._in_transaction:
            self._conn.rollback()
            self._in_transaction = False

    def close(self):
        """关闭数据库连接"""
        if self._conn is not None:
            if self._in_transaction:
                self._conn.rollback()
                self._in_transaction = False
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params: Union[tuple, Dict[str, Any], None] = None) -> int:
        """
        执行 INSERT / UPDATE / DELETE 语句
        :return: 影响的行数
        """
        conn = self.connect()
        cursor = conn.execute(sql, params or ())
        if not self._in_transaction:
            conn.commit()
        return cursor.rowcount

    def fetchone(self, sql: str, params: Union[tuple, Dict[str, Any], None] = None) -> Optional[Dict[str, Any]]:
        """查询单条记录，返回字典或 None"""
        conn = self.connect()
        cursor = conn.execute(sql, params or ())
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self, sql: str, params: Union[tuple, Dict[str, Any], None] = None) -> List[Dict[str, Any]]:
        """查询多条记录，返回字典列表"""
        conn = self.connect()
        cursor = conn.execute(sql, params or ())
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
        """
        插入一条记录
        :return: 影响的行数
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        return self.execute(sql, tuple(data.values()))

    def update(self, table_name: str, data: Dict[str, Any], condition: Dict[str, Any]) -> int:
        """
        更新记录
        :param table_name: 表名
        :param data: 要更新的字段字典
        :param condition: 条件字段字典，如 {"id": 1}
        :return: 影响的行数
        """
        set_clause = ", ".join(f"{k} = ?" for k in data)
        where_clause = " AND ".join(f"{k} = ?" for k in condition)
        sql = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
        params = tuple(data.values()) + tuple(condition.values())
        return self.execute(sql, params)

    def delete(self, table_name: str, condition: Dict[str, Any]) -> int:
        """
        删除记录
        :param table_name: 表名
        :param condition: 条件字段字典，如 {"id": 1}
        :return: 影响的行数
        """
        where_clause = " AND ".join(f"{k} = ?" for k in condition)
        sql = f"DELETE FROM {table_name} WHERE {where_clause}"
        return self.execute(sql, tuple(condition.values()))
