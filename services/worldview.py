from typing import Dict, List, Optional

from RPA_langGraph.entities import WorldviewCollection, WorldviewEntry
from services.base import BaseService
from services.id_utils import generate_wvc_id, generate_wve_id, now


class WorldviewCollectionService(BaseService):
    def create(self, data: Dict) -> WorldviewCollection:
        data.setdefault("worldviewCollectionID", generate_wvc_id(data.get("worldviewCollectionName", "")))
        data.setdefault("recordCreatedTime", now())
        data.setdefault("recordUpdatedTime", now())
        entity = WorldviewCollection(**data)
        self._insert("worldview_collection", dict(entity))
        return entity

    def get(self, worldview_collection_id: str) -> Optional[WorldviewCollection]:
        row = self._get("worldview_collection", "worldviewCollectionID", worldview_collection_id)
        return WorldviewCollection(**row) if row else None

    def update(self, worldview_collection_id: str, data: dict) -> int:
        return self._update("worldview_collection", "worldviewCollectionID", worldview_collection_id, data)

    def delete_cascade(self, worldview_collection_id: str) -> int:
        self.db.execute("DELETE FROM worldview_entry WHERE parentID = ?", (worldview_collection_id,))
        self.db.execute(
            "UPDATE session SET worldviewCollectionID = '' WHERE worldviewCollectionID = ?", (worldview_collection_id,)
        )
        return self._delete("worldview_collection", "worldviewCollectionID", worldview_collection_id)

    def list_all(self) -> List[WorldviewCollection]:
        return [WorldviewCollection(**row) for row in self._list("worldview_collection")]


class WorldviewEntryService(BaseService):
    def create(self, data: Dict) -> WorldviewEntry:
        data.setdefault("worldviewCollectionEntryID", generate_wve_id())
        data.setdefault("isPermanent", False)
        data.setdefault("recordCreatedTime", now())
        data.setdefault("recordUpdatedTime", now())
        entity_data = dict(data)
        entity_data["isPermanent"] = int(entity_data["isPermanent"])
        self._insert("worldview_entry", entity_data)
        data["isPermanent"] = bool(data["isPermanent"])
        return WorldviewEntry(**data)

    def get(self, entry_id: str) -> Optional[WorldviewEntry]:
        row = self._get("worldview_entry", "worldviewCollectionEntryID", entry_id)
        if row:
            row["isPermanent"] = bool(row["isPermanent"])
            return WorldviewEntry(**row)
        return None

    def update(self, entry_id: str, data: dict) -> int:
        if "isPermanent" in data:
            data["isPermanent"] = int(data["isPermanent"])
        return self._update("worldview_entry", "worldviewCollectionEntryID", entry_id, data)

    def delete_cascade(self, entry_id: str) -> int:
        return self._delete("worldview_entry", "worldviewCollectionEntryID", entry_id)

    def list_all(self) -> List[WorldviewEntry]:
        rows = self._list("worldview_entry")
        for r in rows:
            r["isPermanent"] = bool(r["isPermanent"])
        return [WorldviewEntry(**row) for row in rows]

    def list_by_collection(self, parent_id: str) -> List[WorldviewEntry]:
        rows = self._list("worldview_entry", "parentID = ?", (parent_id,))
        for r in rows:
            r["isPermanent"] = bool(r["isPermanent"])
        return [WorldviewEntry(**row) for row in rows]
