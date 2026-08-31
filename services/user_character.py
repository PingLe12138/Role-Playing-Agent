from typing import Dict, List, Optional

from RPA_langGraph.entities import UserCharacterInfoCard
from services.base import BaseService
from services.id_utils import generate_user_character_id, now


class UserCharacterInfoCardService(BaseService):
    def create(self, data: Dict) -> UserCharacterInfoCard:
        data.setdefault("userCharacterID", generate_user_character_id(data.get("userCharacterName", "")))
        data.setdefault("recordCreatedTime", now())
        data.setdefault("recordUpdatedTime", now())
        entity = UserCharacterInfoCard(**data)
        self._insert("user_character_info_card", dict(entity))
        return entity

    def get(self, user_character_id: str) -> Optional[UserCharacterInfoCard]:
        row = self._get("user_character_info_card", "userCharacterID", user_character_id)
        return UserCharacterInfoCard(**row) if row else None

    def update(self, user_character_id: str, data: dict) -> int:
        return self._update("user_character_info_card", "userCharacterID", user_character_id, data)

    def delete_cascade(self, user_character_id: str) -> int:
        self.db.execute("UPDATE session SET userCharacterID = '' WHERE userCharacterID = ?", (user_character_id,))
        return self._delete("user_character_info_card", "userCharacterID", user_character_id)

    def list_all(self) -> List[UserCharacterInfoCard]:
        return [UserCharacterInfoCard(**row) for row in self._list("user_character_info_card")]
