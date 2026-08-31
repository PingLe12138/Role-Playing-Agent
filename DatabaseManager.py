from typing import Optional

from SQLiteClient import SQLiteClient

CREATE_TABLE_SQL = {
    "character_info_card": """
        CREATE TABLE IF NOT EXISTS character_info_card (
            characterID TEXT PRIMARY KEY,
            characterName TEXT NOT NULL,
            characterInfo TEXT,
            recordCreatedTime TEXT,
            recordUpdatedTime TEXT
        )
    """,
    "user_character_info_card": """
        CREATE TABLE IF NOT EXISTS user_character_info_card (
            userCharacterID TEXT PRIMARY KEY,
            userCharacterName TEXT NOT NULL,
            userCharacterInfo TEXT,
            recordCreatedTime TEXT,
            recordUpdatedTime TEXT
        )
    """,
    "worldview_collection": """
        CREATE TABLE IF NOT EXISTS worldview_collection (
            worldviewCollectionID TEXT PRIMARY KEY,
            worldviewCollectionName TEXT NOT NULL,
            worldviewDescription TEXT,
            recordCreatedTime TEXT,
            recordUpdatedTime TEXT
        )
    """,
    "worldview_entry": """
        CREATE TABLE IF NOT EXISTS worldview_entry (
            worldviewCollectionEntryID TEXT PRIMARY KEY,
            parentID TEXT,
            worldviewCollectionEntryContent TEXT,
            isPermanent INTEGER,
            recordCreatedTime TEXT,
            recordUpdatedTime TEXT,
            FOREIGN KEY (parentID) REFERENCES worldview_collection(worldviewCollectionID)
        )
    """,
    "session": """
        CREATE TABLE IF NOT EXISTS session (
            sessionID TEXT PRIMARY KEY,
            worldviewCollectionID TEXT,
            sessionTitle TEXT,
            userCharacterID TEXT,
            sessionPresentCharacter TEXT DEFAULT '[]',
            sessionDepartedCharacter TEXT DEFAULT '[]',
            sessionEnvData TEXT DEFAULT '{}',
            sessionPendingChoice TEXT,
            memoryRoundCounter INTEGER DEFAULT 0,
            outline TEXT,
            status TEXT,
            recordCreatedTime TEXT,
            recordUpdatedTime TEXT,
            FOREIGN KEY (worldviewCollectionID) REFERENCES worldview_collection(worldviewCollectionID)
        )
    """,
    "session_history": """
        CREATE TABLE IF NOT EXISTS session_history (
            sessionHistoryID TEXT PRIMARY KEY,
            parentID TEXT,
            role TEXT,
            createdBy TEXT,
            content TEXT,
            recordCreatedTime TEXT,
            recordUpdatedTime TEXT,
            FOREIGN KEY (parentID) REFERENCES session(sessionID)
        )
    """,
    "memory": """
        CREATE TABLE IF NOT EXISTS memory (
            memoryID TEXT PRIMARY KEY,
            sessionID TEXT,
            characterID TEXT,
            content TEXT,
            recordCreatedTime TEXT,
            recordUpdatedTime TEXT,
            FOREIGN KEY (sessionID) REFERENCES session(sessionID),
            FOREIGN KEY (characterID) REFERENCES character_info_card(characterID)
        )
    """,
    "character_relationship": """
        CREATE TABLE IF NOT EXISTS character_relationship (
            relationshipID TEXT PRIMARY KEY,
            sessionID TEXT NOT NULL,
            characterID_1 TEXT NOT NULL,
            characterID_2 TEXT NOT NULL,
            relationship_type TEXT DEFAULT 'neutral',
            strength REAL DEFAULT 0.5,
            sentiment REAL DEFAULT 0.0,
            power_dynamic REAL DEFAULT 0.0,
            recordCreatedTime TEXT,
            recordUpdatedTime TEXT,
            FOREIGN KEY (sessionID) REFERENCES session(sessionID),
            FOREIGN KEY (characterID_1) REFERENCES character_info_card(characterID),
            FOREIGN KEY (characterID_2) REFERENCES character_info_card(characterID)
        )
    """,
    "character_emotion_state": """
        CREATE TABLE IF NOT EXISTS character_emotion_state (
            emotionStateID TEXT PRIMARY KEY,
            sessionID TEXT NOT NULL,
            characterID TEXT NOT NULL,
            emotionLabel TEXT,
            valence REAL DEFAULT 0.0,
            arousal REAL DEFAULT 0.5,
            intensity REAL DEFAULT 0.0,
            energy REAL DEFAULT 1.0,
            stress REAL DEFAULT 0.0,
            triggerSummary TEXT,
            recordCreatedTime TEXT,
            FOREIGN KEY (sessionID) REFERENCES session(sessionID),
            FOREIGN KEY (characterID) REFERENCES character_info_card(characterID)
        )
    """,
}


class DatabaseManager:
    def __init__(self, db_name: str = "rpa_data.db", db_dir: Optional[str] = None):
        # db_dir 缺省锚定项目根 data/（由 SQLiteClient 处理），显式传入原样生效
        self.db = SQLiteClient(db_name, db_dir)

    def _drop_old_relationship_schema(self, conn):
        try:
            cursor = conn.execute("PRAGMA table_info(character_relationship)")
            cols = {row[1] for row in cursor.fetchall()}
            if "sourceID" in cols or "targetID" in cols:
                conn.execute("DROP TABLE IF EXISTS character_relationship")
        except Exception:
            pass

    def create_tables(self):
        conn = self.db.connect()
        conn.execute("PRAGMA foreign_keys = ON")
        self._drop_old_relationship_schema(conn)
        for table_name, sql in CREATE_TABLE_SQL.items():
            self.db.execute(sql)
        migrations = [
            "ALTER TABLE session ADD COLUMN userCharacterID TEXT",
            "ALTER TABLE session ADD COLUMN sessionPresentCharacter TEXT DEFAULT '[]'",
            "ALTER TABLE session ADD COLUMN sessionDepartedCharacter TEXT DEFAULT '[]'",
            "ALTER TABLE session ADD COLUMN sessionEnvData TEXT DEFAULT '{}'",
            "ALTER TABLE session ADD COLUMN sessionPendingChoice TEXT",
            "ALTER TABLE session ADD COLUMN memoryRoundCounter INTEGER DEFAULT 0",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
            except Exception:
                pass

        try:
            conn.execute("ALTER TABLE worldview_entry RENAME COLUMN isPermanented TO isPermanent")
        except Exception:
            pass

        # migration: add defaultRelationships to character_info_card
        try:
            conn.execute("ALTER TABLE character_info_card ADD COLUMN defaultRelationships TEXT DEFAULT '[]'")
        except Exception:
            pass

        # migration: add initialEmotion to character_info_card
        try:
            conn.execute("ALTER TABLE character_info_card ADD COLUMN initialEmotion TEXT")
        except Exception:
            pass

        # migration: add defaultRelationships to user_character_info_card
        try:
            conn.execute("ALTER TABLE user_character_info_card ADD COLUMN defaultRelationships TEXT DEFAULT '[]'")
        except Exception:
            pass

    def close(self):
        self.db.close()


if __name__ == "__main__":
    mgr = DatabaseManager()
    mgr.create_tables()
    print("All 9 tables created successfully in ./data/rpa_data.db")
    mgr.close()
