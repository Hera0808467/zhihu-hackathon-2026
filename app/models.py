"""数据模型"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import time, uuid


class InputMode(str, Enum):
    NARRATION = "narration"
    FIXED = "fixed"
    GUIDED = "guided"
    FREE = "free"


class SpeakerType(str, Enum):
    PLAYER = "player"
    BOT = "bot"
    NARRATOR = "narrator"
    SYSTEM = "system"


class GameStatus(str, Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"


# ── 剧本数据结构 ──

class RoleProfile(BaseModel):
    role_id: str
    name: str
    identity: str
    personality: str
    speaking_style: str
    core_purpose: str
    trigger_points: list[str] = []
    weakness: str = ""
    playable: bool = True
    required: bool = False
    avatar_prompt: str = ""


class Segment(BaseModel):
    speaker: str = "旁白"
    speaker_type: SpeakerType = SpeakerType.NARRATOR
    text: str
    input_mode: InputMode = InputMode.NARRATION
    guided_options: list[str] = []
    emotion_tag: str = ""
    card_type: str = ""  # 剧情背景/旧事回忆/人物档案/当前线索


class Choice(BaseModel):
    text: str
    next: str
    condition: str = ""
    changes: dict = {}  # val, flags, variables changes
    effect: str = ""
    influence_hint: str = ""  # "裴琰更愿意靠近你" 而非 "+10好感"


class RouteCondition(BaseModel):
    condition: str
    next: str


class StoryNode(BaseModel):
    node_id: str
    act: int = 1
    act_title: str = ""
    scene_name: str = ""
    scene_description: str = ""
    ambient: str = ""
    segments: list[Segment] = []
    choices: list[Choice] = []
    routes: list[RouteCondition] = []
    is_ending: bool = False
    ending_type: str = ""  # 圆满/遗憾/隐藏
    ending_title: str = ""
    ending_description: str = ""
    ending_closing: str = ""
    progress: int = 0  # 0-100


class StoryMeta(BaseModel):
    story_id: str
    title: str
    author: str
    source_url: str = ""
    genre: str = ""
    world_setting: str = ""
    max_players: int = 5
    min_players: int = 1
    roles: list[RoleProfile] = []
    start_node_id: str = "start"


class StoryScript(BaseModel):
    meta: StoryMeta
    nodes: dict[str, StoryNode]  # node_id -> StoryNode


# ── 运行时数据结构 ──

class GameSession(BaseModel):
    game_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8].upper())
    story_id: str = ""
    status: GameStatus = GameStatus.WAITING
    current_node_id: str = ""
    current_act: int = 1
    player_roles: dict[str, str] = {}  # user_id -> role_id
    bot_roles: list[str] = []
    val: int = 50
    flags: list[str] = []
    variables: dict[str, int] = {}  # 各角色亲密度等
    waiting_for: str = ""  # user_id or "bot"
    free_count_used: int = 0
    history: list[dict] = []  # 对话历史
    created_at: float = Field(default_factory=time.time)
    snapshots: list[dict] = []  # 用于回溯


class GameResult(BaseModel):
    game_id: str
    ending_type: str
    ending_title: str
    ending_description: str
    ending_closing: str
    highlights: list[dict] = []
    relationship_graph: dict[str, int] = {}
    stats: dict = {}
