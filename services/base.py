from typing import Any, Dict, List, Optional

from SQLiteClient import SQLiteClient


class BaseService:
    def __init__(self, db: SQLiteClient):
        self.db = db

    def _insert(self, table: str, data: Dict[str, Any]) -> int:
        return self.db.insert(table, data)

    def _get(self, table: str, id_field: str, id_value: str) -> Optional[Dict[str, Any]]:
        return self.db.fetchone(f"SELECT * FROM {table} WHERE {id_field} = ?", (id_value,))

    def _update(self, table: str, id_field: str, id_value: str, data: Dict[str, Any]) -> int:
        return self.db.update(table, data, {id_field: id_value})

    def _delete(self, table: str, id_field: str, id_value: str) -> int:
        return self.db.delete(table, {id_field: id_value})

    def _list(self, table: str, where: str = "", params: tuple = ()) -> List[Dict[str, Any]]:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return self.db.fetchall(sql, params)
