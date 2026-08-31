from typing import TypedDict

from RPA_langGraph.AgentState import EnvData


class CharacterInfoCard(TypedDict):
    characterID: str
    characterName: str
    characterInfo: str
    recordCreatedTime: str
    recordUpdatedTime: str


class UserCharacterInfoCard(TypedDict):
    userCharacterID: str
    userCharacterName: str
    userCharacterInfo: str
    defaultRelationships: str
    recordCreatedTime: str
    recordUpdatedTime: str


class WorldviewCollection(TypedDict):
    worldviewCollectionID: str
    worldviewCollectionName: str
    worldviewDescription: str
    recordCreatedTime: str
    recordUpdatedTime: str


class WorldviewEntry(TypedDict):
    worldviewCollectionEntryID: str
    parentID: str
    worldviewCollectionEntryContent: str
    isPermanent: bool
    recordCreatedTime: str
    recordUpdatedTime: str


class Session(TypedDict):
    sessionID: str
    worldviewCollectionID: str
    sessionTitle: str
    userCharacterID: str
    sessionPresentCharacter: list[str]
    sessionDepartedCharacter: list[str]
    sessionEnvData: EnvData
    sessionPendingChoice: dict
    memoryRoundCounter: int
    outline: list[str]
    status: str
    recordCreatedTime: str
    recordUpdatedTime: str


class SessionHistory(TypedDict):
    sessionHistoryID: str
    parentID: str
    role: str
    createdBy: str
    content: str
    recordCreatedTime: str
    recordUpdatedTime: str
