import os
import tempfile

from langchain_core.messages import AIMessage, HumanMessage
import pytest

from SQLiteClient import SQLiteClient


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    client = SQLiteClient(os.path.basename(path), db_dir=os.path.dirname(path))
    client.execute(
        "CREATE TABLE character_info_card (characterID TEXT PRIMARY KEY, characterName TEXT, characterInfo TEXT, recordCreatedTime TEXT, recordUpdatedTime TEXT)"
    )
    client.execute(
        "CREATE TABLE user_character_info_card (userCharacterID TEXT PRIMARY KEY, userCharacterName TEXT, userCharacterInfo TEXT, recordCreatedTime TEXT, recordUpdatedTime TEXT)"
    )
    client.execute(
        "CREATE TABLE worldview_entry (worldviewCollectionEntryID TEXT PRIMARY KEY, parentID TEXT, worldviewCollectionEntryContent TEXT, isPermanent INTEGER, recordCreatedTime TEXT, recordUpdatedTime TEXT)"
    )
    client.execute(
        "CREATE TABLE memory (memoryID TEXT PRIMARY KEY, sessionID TEXT, characterID TEXT, content TEXT, recordCreatedTime TEXT, recordUpdatedTime TEXT)"
    )
    client.execute(
        "CREATE TABLE session (sessionID TEXT PRIMARY KEY, sessionTitle TEXT, sessionPresentCharacter TEXT, sessionDepartedCharacter TEXT, sessionEnvData TEXT, sessionPendingChoice TEXT, memoryRoundCounter INTEGER DEFAULT 0, outline TEXT, recordCreatedTime TEXT, recordUpdatedTime TEXT)"
    )
    client.execute(
        "CREATE TABLE session_history (sessionHistoryID TEXT PRIMARY KEY, parentID TEXT, role TEXT, createdBy TEXT, content TEXT, recordCreatedTime TEXT, recordUpdatedTime TEXT)"
    )
    yield client
    client.close()
    try:
        os.unlink(path)
    except PermissionError:
        pass


@pytest.fixture
def sample_messages():
    return [
        HumanMessage(content="你好"),
        AIMessage(content="你好！有什么可以帮你的吗？"),
        HumanMessage(content="我们开始冒险吧"),
    ]
