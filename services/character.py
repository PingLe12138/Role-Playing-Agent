import json
from typing import Dict, List, Optional

from RPA_langGraph.entities import CharacterInfoCard
from services.base import BaseService
from services.id_utils import generate_character_id, now


class CharacterInfoCardService(BaseService):
    def create(self, data: Dict) -> CharacterInfoCard:
        data.setdefault("characterID", generate_character_id(data.get("characterName", "")))
        data.setdefault("recordCreatedTime", now())
        data.setdefault("recordUpdatedTime", now())
        entity = CharacterInfoCard(**data)
        self._insert("character_info_card", dict(entity))
        return entity

    def get(self, character_id: str) -> Optional[CharacterInfoCard]:
        row = self._get("character_info_card", "characterID", character_id)
        return CharacterInfoCard(**row) if row else None

    def update(self, character_id: str, data: dict) -> int:
        return self._update("character_info_card", "characterID", character_id, data)

    def delete_cascade(self, character_id: str) -> int:
        self.db.execute("DELETE FROM memory WHERE characterID = ?", (character_id,))
        sessions = self.db.fetchall("SELECT sessionID, sessionPresentCharacter FROM session")
        for sess in sessions:
            try:
                chars = json.loads(sess["sessionPresentCharacter"])
            except (json.JSONDecodeError, TypeError):
                chars = []
            if character_id in chars:
                chars.remove(character_id)
                self.db.execute(
                    "UPDATE session SET sessionPresentCharacter = ? WHERE sessionID = ?",
                    (json.dumps(chars, ensure_ascii=False), sess["sessionID"]),
                )
        return self._delete("character_info_card", "characterID", character_id)

    def list_all(self) -> List[CharacterInfoCard]:
        return [CharacterInfoCard(**row) for row in self._list("character_info_card")]
