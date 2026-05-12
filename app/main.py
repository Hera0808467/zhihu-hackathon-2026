"""FastAPI 主应用"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pydantic import BaseModel
from typing import Optional
import json, uuid, asyncio, httpx, traceback

from app.models import GameSession, GameResult, GameStatus
from app.engine import evaluate_condition, apply_changes, resolve_next_node, save_snapshot, rollback
from app.story_data import HUATANGCHUN

app = FastAPI(title="画堂春互动文游", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 内存存储 ──
STORIES = {"huatangchun": HUATANGCHUN}
SESSIONS: dict[str, GameSession] = {}
CONNECTIONS: dict[str, list[WebSocket]] = {}  # game_id -> ws 列表


# ── 广播工具 ──
async def broadcast(game_id: str, event: str, data: dict):
    if game_id not in CONNECTIONS:
        return
    msg = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    dead = []
    for ws in CONNECTIONS[game_id]:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CONNECTIONS[game_id].remove(ws)


def get_session(game_id: str) -> GameSession:
    if game_id not in SESSIONS:
        raise HTTPException(404, f"房间 {game_id} 不存在")
    return SESSIONS[game_id]


def node_to_dict(game_id: str) -> dict:
    """返回当前节点的展示数据"""
    s = SESSIONS[game_id]
    story = STORIES[s.story_id]
    node = story.nodes[s.current_node_id]
    # 过滤 choices（根据条件）
    visible_choices = [
        {"index": i, "text": c.text, "influence_hint": c.influence_hint}
        for i, c in enumerate(node.choices)
        if evaluate_condition(c.condition, s)
    ]
    return {
        "node_id": node.node_id,
        "act": node.act,
        "act_title": node.act_title,
        "scene_name": node.scene_name,
        "scene_description": node.scene_description,
        "ambient": node.ambient,
        "progress": node.progress,
        "segments": [seg.model_dump() for seg in node.segments],
        "choices": visible_choices,
        "is_ending": node.is_ending,
        "ending_type": node.ending_type if node.is_ending else "",
        "ending_title": node.ending_title if node.is_ending else "",
        "ending_description": node.ending_description if node.is_ending else "",
        "ending_closing": node.ending_closing if node.is_ending else "",
        "waiting_for": s.waiting_for,
    }


# ── 1. 游戏生命周期 ──

class CreateRequest(BaseModel):
    story_id: str = "huatangchun"

@app.post("/api/games/create")
def create_game(req: CreateRequest):
    if req.story_id not in STORIES:
        raise HTTPException(404, "故事不存在")
    story = STORIES[req.story_id]
    s = GameSession(story_id=req.story_id)
    s.current_node_id = story.meta.start_node_id
    SESSIONS[s.game_id] = s
    return {
        "game_id": s.game_id,
        "story_meta": {
            "title": story.meta.title,
            "author": story.meta.author,
            "genre": story.meta.genre,
            "world_setting": story.meta.world_setting,
        },
        "roles": [r.model_dump() for r in story.meta.roles],
        "status": s.status,
    }


class JoinRequest(BaseModel):
    user_id: str
    role_id: str

@app.post("/api/games/{game_id}/join")
def join_game(game_id: str, req: JoinRequest):
    s = get_session(game_id)
    if s.status != GameStatus.WAITING:
        raise HTTPException(400, "游戏已开始，无法加入")
    # 校验角色是否已被占
    if req.role_id in s.player_roles.values():
        raise HTTPException(400, f"角色 {req.role_id} 已被选择")
    # 校验角色是否存在
    story = STORIES[s.story_id]
    role_ids = [r.role_id for r in story.meta.roles]
    if req.role_id not in role_ids:
        raise HTTPException(400, f"角色 {req.role_id} 不存在")
    s.player_roles[req.user_id] = req.role_id
    return {
        "game_id": game_id,
        "player_roles": s.player_roles,
        "remaining_roles": [r for r in role_ids if r not in s.player_roles.values()],
    }


@app.post("/api/games/{game_id}/start")
async def start_game(game_id: str):
    s = get_session(game_id)
    story = STORIES[s.story_id]
    # Bot 补位：未选的角色都由 Bot 扮演
    all_roles = [r.role_id for r in story.meta.roles]
    s.bot_roles = [r for r in all_roles if r not in s.player_roles.values()]
    # 初始化亲密度变量
    for role in all_roles:
        s.variables[f"wentang_{role}"] = 0
    s.status = GameStatus.PLAYING
    # 设置 waiting_for（主角玩家）
    wentang_user = next((u for u, r in s.player_roles.items() if r == "wentang"), "bot")
    s.waiting_for = wentang_user
    await broadcast(game_id, "game_start", node_to_dict(game_id))
    return {"status": "playing", **node_to_dict(game_id)}


@app.get("/api/games/{game_id}")
def get_game(game_id: str):
    s = get_session(game_id)
    return {**s.model_dump(), "current_node": node_to_dict(game_id)}


# ── 2. 游戏核心交互 ──

class ChooseRequest(BaseModel):
    user_id: str
    choice_index: int

@app.post("/api/games/{game_id}/choose")
async def choose(game_id: str, req: ChooseRequest):
    s = get_session(game_id)
    if s.status != GameStatus.PLAYING:
        raise HTTPException(400, "游戏未在进行中")
    story = STORIES[s.story_id]
    node = story.nodes[s.current_node_id]
    # 过滤有效选项
    visible = [c for c in node.choices if evaluate_condition(c.condition, s)]
    if req.choice_index >= len(visible):
        raise HTTPException(400, "选项不存在")
    choice = visible[req.choice_index]
    # 保存快照
    save_snapshot(s)
    # 应用变化
    apply_changes(choice.changes, s)
    # 记录历史
    s.history.append({
        "type": "choice",
        "user_id": req.user_id,
        "text": choice.text,
        "changes": choice.changes,
    })
    # 跳转节点
    next_node = story.nodes.get(choice.next)
    if not next_node:
        raise HTTPException(500, f"节点 {choice.next} 不存在")
    s.current_node_id = choice.next
    # 如果是结局节点
    if next_node.is_ending:
        s.status = GameStatus.FINISHED
        result = build_result(game_id)
        await broadcast(game_id, "game_end", result)
        return {"status": "finished", "result": result}
    # 通过 routes 自动路由（如果下一节点有 routes）
    resolved = resolve_next_node(next_node, s)
    if resolved:
        s.current_node_id = resolved
        final_node = story.nodes.get(resolved)
        if final_node and final_node.is_ending:
            s.status = GameStatus.FINISHED
            result = build_result(game_id)
            await broadcast(game_id, "game_end", result)
            return {"status": "finished", "result": result}
    # 广播新节点
    node_data = node_to_dict(game_id)
    await broadcast(game_id, "node_update", node_data)
    # 状态变化广播
    await broadcast(game_id, "state_change", {
        "changes": choice.changes,
        "val": s.val,
        "flags": s.flags,
        "variables": s.variables,
        "influence_hint": choice.influence_hint,
    })
    return node_data


class SpeakRequest(BaseModel):
    user_id: str
    text: str

@app.post("/api/games/{game_id}/speak")
async def speak(game_id: str, req: SpeakRequest):
    s = get_session(game_id)
    if s.free_count_used >= 5:
        raise HTTPException(400, "自由对话次数已用完（每局限5次）")
    story = STORIES[s.story_id]
    role_id = s.player_roles.get(req.user_id, "wentang")
    role = next((r for r in story.meta.roles if r.role_id == role_id), None)
    # 记录历史
    s.history.append({"type": "free", "user_id": req.user_id, "role": role_id, "text": req.text})
    s.free_count_used += 1
    # 调用 AI 生成回复（简化版：直接返回，后续接入API）
    ai_reply = await generate_ai_reply(s, story, role_id, req.text)
    reply_data = {
        "speaker": role.name if role else role_id,
        "speaker_type": "player",
        "text": req.text,
        "emotion_tag": "",
    }
    bot_reply = {
        "speaker": ai_reply["speaker"],
        "speaker_type": "bot",
        "text": ai_reply["text"],
        "emotion_tag": ai_reply.get("emotion", ""),
    }
    s.history.append({"type": "ai_reply", **bot_reply})
    await broadcast(game_id, "message", reply_data)
    await broadcast(game_id, "message", bot_reply)
    return {"user_message": reply_data, "ai_reply": bot_reply, "free_count_remaining": 5 - s.free_count_used}


class RollbackRequest(BaseModel):
    steps: int = 1

@app.post("/api/games/{game_id}/rollback")
async def do_rollback(game_id: str, req: RollbackRequest):
    s = get_session(game_id)
    ok = rollback(s, req.steps)
    if not ok:
        raise HTTPException(400, "没有可回溯的记录")
    node_data = node_to_dict(game_id)
    await broadcast(game_id, "node_update", node_data)
    return node_data


@app.post("/api/games/{game_id}/finish")
def finish_game(game_id: str):
    s = get_session(game_id)
    s.status = GameStatus.FINISHED
    return build_result(game_id)


# ── 3. 故事列表 ──

@app.get("/api/stories")
def list_stories():
    return [
        {"story_id": sid, "title": s.meta.title, "author": s.meta.author,
         "genre": s.meta.genre, "max_players": s.meta.max_players}
        for sid, s in STORIES.items()
    ]


# ── 4. WebSocket ──

@app.websocket("/ws/games/{game_id}")
async def ws_endpoint(websocket: WebSocket, game_id: str, user_id: str = "guest"):
    if game_id not in SESSIONS:
        await websocket.close(code=4004)
        return
    await websocket.accept()
    if game_id not in CONNECTIONS:
        CONNECTIONS[game_id] = []
    CONNECTIONS[game_id].append(websocket)
    # 发送当前节点状态
    await websocket.send_text(json.dumps({
        "event": "connected",
        "data": node_to_dict(game_id)
    }, ensure_ascii=False))
    try:
        while True:
            await websocket.receive_text()  # 保持连接（ping/pong）
    except WebSocketDisconnect:
        if websocket in CONNECTIONS.get(game_id, []):
            CONNECTIONS[game_id].remove(websocket)
        await broadcast(game_id, "player_leave", {"user_id": user_id})


# ── 工具函数 ──

def build_result(game_id: str) -> dict:
    s = SESSIONS[game_id]
    story = STORIES[s.story_id]
    node = story.nodes[s.current_node_id]
    # 高光时刻
    highlights = []
    for h in s.history:
        if h.get("type") == "choice":
            changes = h.get("changes", {})
            if any(abs(v) >= 15 for v in changes.values() if isinstance(v, int)):
                highlights.append({"text": h["text"], "type": "关键选择"})
    # 关系图谱
    rel = {k.replace("wentang_", ""): v for k, v in s.variables.items() if k.startswith("wentang_")}
    return {
        "game_id": game_id,
        "ending_type": node.ending_type if node.is_ending else "未完成",
        "ending_title": node.ending_title if node.is_ending else "",
        "ending_description": node.ending_description if node.is_ending else "",
        "ending_closing": node.ending_closing if node.is_ending else "",
        "highlights": highlights[:5],
        "relationship_graph": rel,
        "stats": {
            "choices_made": sum(1 for h in s.history if h.get("type") == "choice"),
            "free_count_used": s.free_count_used,
            "flags_unlocked": len(s.flags),
            "val_final": s.val,
        },
    }


LLM_BASE_URL = "https://pi-api.macaron.xin/v1"
LLM_API_KEY = "sk-037732ff42ca360ba8ee4e84a3f71e6bed8885567a36686271cdba2bbcb540f5"
LLM_MODEL = "gpt-5.5"

async def generate_ai_reply(session: GameSession, story, player_role_id: str, user_text: str) -> dict:
    """AI 回复生成"""
    # 找一个合适的 Bot 角色来回复
    story_node = story.nodes[session.current_node_id]
    bot_role = None
    # 优先找当前节点中的 Bot 角色
    for seg in story_node.segments:
        if seg.speaker_type.value == "bot":
            bot_role = next((r for r in story.meta.roles if r.name == seg.speaker), None)
            if bot_role:
                break
    # 没找到就找 Bot 列表里第一个
    if not bot_role and session.bot_roles:
        bot_role = next((r for r in story.meta.roles if r.role_id in session.bot_roles), None)
    if not bot_role:
        bot_role = next((r for r in story.meta.roles if r.role_id != player_role_id), None)
    
    player_role = next((r for r in story.meta.roles if r.role_id == player_role_id), None)
    player_name = player_role.name if player_role else "玩家"
    
    # 构建对话历史
    recent = session.history[-6:] if len(session.history) > 6 else session.history
    history_text = "\n".join(
        f"{h.get('role', '?')}: {h.get('text', '')}" for h in recent if h.get('text')
    )
    
    system_prompt = f"""你是《画堂春》中的{bot_role.name}。
身份：{bot_role.identity}
性格：{bot_role.personality}
说话风格：{bot_role.speaking_style}
核心目的：{bot_role.core_purpose}
弱点：{bot_role.weakness}

世界观：{story.meta.world_setting}
当前场景：{story_node.scene_name} - {story_node.scene_description}

规则：
- 严格保持角色一致性，用{bot_role.name}的口吻说话
- 回复简短有力，不超过80字
- 不要用括号描述动作，直接说台词
- 可以根据对方的话调整情绪和态度"""

    messages = [
        {"role": "system", "content": system_prompt},
    ]
    if history_text:
        messages.append({"role": "user", "content": f"之前的对话：\n{history_text}"})
    messages.append({"role": "user", "content": f"{player_name}对你说：「{user_text}」"})
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                json={"model": LLM_MODEL, "messages": messages, "max_tokens": 150, "temperature": 0.8},
            )
            data = r.json()
            reply_text = data["choices"][0]["message"]["content"].strip()
            return {"speaker": bot_role.name, "text": reply_text, "emotion": ""}
    except Exception as e:
        traceback.print_exc()
        return {"speaker": bot_role.name, "text": f"（{bot_role.name}沉默片刻…）", "emotion": "沉默"}


# ── 静态文件 & 首页 ──

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)


# ── 5. OAuth 登录 ──

OAUTH_APP_ID = ""  # 黑客松广场创建项目后填入
OAUTH_APP_KEY = ""  # 同上
OAUTH_REDIRECT_URI = ""  # 部署后的回调地址

@app.get("/api/auth/login")
def oauth_login(redirect_uri: str = ""):
    """返回知乎 OAuth 授权 URL"""
    uri = redirect_uri or OAUTH_REDIRECT_URI
    if not OAUTH_APP_ID:
        return {"url": "", "msg": "OAuth app_id 未配置，请先在黑客松广场创建项目"}
    auth_url = f"https://openapi.zhihu.com/authorize?redirect_uri={uri}&app_id={OAUTH_APP_ID}&response_type=code"
    return {"url": auth_url}


@app.post("/api/auth/callback")
async def oauth_callback(code: str):
    """用 authorization_code 换取 access_token"""
    if not OAUTH_APP_ID or not OAUTH_APP_KEY:
        raise HTTPException(400, "OAuth 未配置")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://openapi.zhihu.com/oauth/access_token",
            json={"app_id": OAUTH_APP_ID, "app_key": OAUTH_APP_KEY, "code": code},
        )
        data = r.json()
    if "access_token" not in data:
        raise HTTPException(400, f"获取 token 失败: {data}")
    # 用 token 获取用户信息
    token = data["access_token"]
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://openapi.zhihu.com/oauth/user_info",
            headers={"Authorization": f"Bearer {token}"},
        )
        user_info = r.json()
    return {"access_token": token, "user_info": user_info}


@app.get("/api/auth/user")
async def get_user_info(token: str):
    """用 access_token 获取用户信息"""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://openapi.zhihu.com/oauth/user_info",
            headers={"Authorization": f"Bearer {token}"},
        )
        return r.json()
