from typing import Any, Optional

from pydantic import BaseModel


class ApiResponse(BaseModel):
    data: Any = None
    msg: str = "ok"


class RelationshipCreate(BaseModel):
    sessionID: str = ""
    characterID_1: str
    characterID_2: str
    relationship_type: str = "neutral"
    strength: float = 0.5
    sentiment: float = 0.0
    power_dynamic: float = 0.0


class RelationshipsBatchCreate(BaseModel):
    relationships: list[RelationshipCreate]


class InitialEmotion(BaseModel):
    emotionLabel: str = "平静"
    valence: float = 0.0
    arousal: float = 0.5
    intensity: float = 0.0
    energy: float = 1.0
    stress: float = 0.0


class CharacterCardCreate(BaseModel):
    characterName: str
    characterInfo: str = ""
    initialEmotion: Optional[InitialEmotion] = None
    relationships: list[RelationshipCreate] = []


class CharacterCardUpdate(BaseModel):
    characterName: Optional[str] = None
    characterInfo: Optional[str] = None
    initialEmotion: Optional[dict] = None
    defaultRelationships: Optional[list[dict]] = None


class CharacterCardExportItem(BaseModel):
    characterName: str
    characterInfo: str = ""
    defaultRelationships: str = "[]"
    initialEmotion: str = "{}"


class CharacterCardExportData(BaseModel):
    version: int = 1
    exported_at: Optional[str] = None
    characters: list[CharacterCardExportItem] = []


class UserCharacterCreate(BaseModel):
    userCharacterName: str
    userCharacterInfo: str = ""
    relationships: list[RelationshipCreate] = []


class UserCharacterUpdate(BaseModel):
    userCharacterName: Optional[str] = None
    userCharacterInfo: Optional[str] = None
    defaultRelationships: Optional[list[dict]] = None


class UserCharacterExportItem(BaseModel):
    userCharacterName: str
    userCharacterInfo: str = ""
    defaultRelationships: str = "[]"


class UserCharacterExportData(BaseModel):
    version: int = 1
    exported_at: Optional[str] = None
    characters: list[UserCharacterExportItem] = []


class WorldviewCollectionCreate(BaseModel):
    worldviewCollectionName: str
    worldviewDescription: str = ""


class WorldviewCollectionUpdate(BaseModel):
    worldviewCollectionName: Optional[str] = None
    worldviewDescription: Optional[str] = None


class WorldviewEntryCreate(BaseModel):
    parentID: str
    worldviewCollectionEntryContent: str
    isPermanent: bool = False


class WorldviewEntryUpdate(BaseModel):
    worldviewCollectionEntryContent: Optional[str] = None
    isPermanent: Optional[bool] = None


class WorldviewExportEntry(BaseModel):
    worldviewCollectionEntryContent: str
    isPermanent: bool = False


class WorldviewExportCollection(BaseModel):
    worldviewCollectionName: str
    worldviewDescription: str = ""


class WorldviewExportData(BaseModel):
    version: int = 1
    exported_at: Optional[str] = None
    collection: WorldviewExportCollection
    entries: list[WorldviewExportEntry] = []


class SessionCreate(BaseModel):
    sessionTitle: str
    worldviewCollectionID: str
    userCharacterID: str = ""
    sessionEnvData: dict = {}
    sessionPresentCharacter: list[str] = []
    initialRelationships: list[RelationshipCreate] = []


class SessionUpdate(BaseModel):
    sessionTitle: Optional[str] = None
    status: Optional[str] = None
    sessionEnvData: Optional[dict] = None
    sessionPresentCharacter: Optional[list[str]] = None
    sessionDepartedCharacter: Optional[list[str]] = None
    sessionPendingChoice: Optional[dict] = None


class SessionHistoryCreate(BaseModel):
    parentID: str
    role: str
    createdBy: str
    content: str


class SessionExportItem(BaseModel):
    sessionTitle: str
    status: str = "active"
    sessionPresentCharacter: list[str] = []
    sessionDepartedCharacter: list[str] = []
    sessionEnvData: dict = {}
    memoryRoundCounter: int = 0
    outline: list[str] = []


class WorldviewExportCollectionInSession(BaseModel):
    worldviewCollectionName: str
    worldviewDescription: str = ""
    entries: list[WorldviewExportEntry] = []


class UserCharacterExportItemInSession(BaseModel):
    userCharacterName: str
    userCharacterInfo: str = ""
    defaultRelationships: str = "[]"


class CharacterExportItemInSession(BaseModel):
    characterName: str
    characterInfo: str = ""
    defaultRelationships: str = "[]"
    initialEmotion: str = "{}"


class HistoryExportItem(BaseModel):
    role: str
    createdBy: str
    content: str


class RelationshipExportItem(BaseModel):
    fromName: str
    toName: str
    relationship_type: str = "neutral"
    strength: float = 0.5
    sentiment: float = 0.0
    power_dynamic: float = 0.0


class EmotionExportItem(BaseModel):
    characterName: str
    emotionLabel: str = "平静"
    valence: float = 0.0
    arousal: float = 0.5
    intensity: float = 0.0
    energy: float = 1.0
    stress: float = 0.0
    triggerSummary: str = ""


class MemoryExportItem(BaseModel):
    characterName: str
    content: str


class SessionExportData(BaseModel):
    version: int = 1
    exported_at: Optional[str] = None
    session: SessionExportItem
    worldviewCollection: Optional[WorldviewExportCollectionInSession] = None
    userCharacter: Optional[UserCharacterExportItemInSession] = None
    characters: list[CharacterExportItemInSession] = []
    history: list[HistoryExportItem] = []
    relationships: list[RelationshipExportItem] = []
    emotionStates: list[EmotionExportItem] = []
    memories: list[MemoryExportItem] = []


class ChatRequest(BaseModel):
    sessionID: str
    message: str


class ConfigUpdate(BaseModel):
    protocol: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    default_temperature: Optional[float] = None
    default_max_tokens: Optional[int] = None
    is_enable_thinking: Optional[str] = None
    default_reasoning_effort: Optional[str] = None
    max_context_tokens: Optional[int] = None


class ConfigTestRequest(BaseModel):
    protocol: str = "openai"
    api_key: str
    base_url: str
    default_model: str


class NodeParamsUpdate(BaseModel):
    node_params: dict


class NodePromptUpdate(BaseModel):
    prompt: str


class SystemRulesUpdate(BaseModel):
    system_rules: str


class NodeContextsUpdate(BaseModel):
    node_contexts: dict


class NodeLlmUpdate(BaseModel):
    """Wholesale replace of the per-node LLM override map (`node_llm`).

    / 整体替换逐节点 LLM 覆盖表（node_llm）。
    """

    node_llm: dict


class FeatureConfigUpdate(BaseModel):
    player_choice_enabled: Optional[bool] = None
    memory_summarize_interval: Optional[int] = None


class NodeConfigUpdate(BaseModel):
    node_params: Optional[dict] = None
    node_prompts: Optional[dict] = None
    node_contexts: Optional[dict] = None
    node_llm: Optional[dict] = None


class ImageGenerationUpdate(BaseModel):
    """Partial update model for the scene-image (ComfyUI) generation section.
    / 场景插画（ComfyUI）配置节的部分更新模型。"""

    enabled: Optional[bool] = None
    comfyui_base_url: Optional[str] = None
    checkpoint: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    cfg: Optional[float] = None
    sampler_name: Optional[str] = None
    scheduler: Optional[str] = None
    negative_prompt: Optional[str] = None
    interval_seconds: Optional[int] = None
    max_per_session: Optional[int] = None
    llm_decision_enabled: Optional[bool] = None
    timeout_seconds: Optional[int] = None
    poll_interval_seconds: Optional[float] = None


class ImageGenerationTestRequest(BaseModel):
    """Optional body for probing a ComfyUI server with the form's current value
    (falls back to the saved config when omitted).  / 可选 body：用表单当前填写
    的 ComfyUI 地址做连通性测试（缺省时回退到已保存配置）。"""

    comfyui_base_url: Optional[str] = None


class NodeConfigExportData(BaseModel):
    version: int = 1
    exported_at: Optional[str] = None
    node_params: dict = {}
    node_prompts: dict = {}
    node_contexts: dict = {}
    system_rules: Optional[str] = None


class SetupCompleteRequest(BaseModel):
    """Mark the first-run setup wizard as done.

    `skipped=True` records that the user dismissed the wizard without
    configuring anything (the wizard then stops nagging but the config keeps
    its current values).  / `skipped=True` 表示用户跳过引导（不再提示，但配置
    保持原样）。
    """

    skipped: bool = False


class LoginRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
