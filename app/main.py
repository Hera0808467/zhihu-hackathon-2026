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
from app.story_data import HUATANGCHUN_WENTANG, HUATANGCHUN_PEIRONG, HUATANGCHUN_MOOK

app = FastAPI(title="画堂春互动文游", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 内存存储 ──
STORIES = {
    "huatangchun": HUATANGCHUN_WENTANG,          # 默认（向后兼容）
    "huatangchun_wentang": HUATANGCHUN_WENTANG,  # 温棠视角
    "huatangchun_peirong": HUATANGCHUN_PEIRONG,  # 裴容视角
    "huatangchun_mook": HUATANGCHUN_MOOK,        # 双人 MOOK 模式
}
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


async def send_to_user(game_id: str, user_id: str, event: str, data: dict):
    """Send event to a specific user's websocket (if connected)"""
    # For now, broadcast to all — proper per-user routing needs user→ws mapping
    await broadcast(game_id, event, data)


async def broadcast_node_per_role(game_id: str, event: str):
    """Broadcast current node to all connections"""
    await broadcast(game_id, event, node_to_dict(game_id))


def get_session(game_id: str) -> GameSession:
    if game_id not in SESSIONS:
        raise HTTPException(404, f"房间 {game_id} 不存在")
    return SESSIONS[game_id]


def node_to_dict(game_id: str, viewer_role: str = "") -> dict:
    """返回当前节点的展示数据，支持按角色返回不同视角"""
    s = SESSIONS[game_id]
    story = STORIES[s.story_id]
    node = story.nodes[s.current_node_id]
    # 根据 viewer_role 选择 segments
    if viewer_role and viewer_role in node.role_segments:
        segments = node.role_segments[viewer_role]
    else:
        segments = node.segments
    # 根据 viewer_role 选择 choices
    if viewer_role and viewer_role in node.role_choices:
        choices_source = node.role_choices[viewer_role]
    else:
        choices_source = node.choices
    # 过滤 choices（根据条件）
    visible_choices = [
        {"index": i, "text": c.text, "influence_hint": c.influence_hint}
        for i, c in enumerate(choices_source)
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
        "segments": [seg.model_dump() for seg in segments],
        "choices": visible_choices,
        "is_ending": node.is_ending,
        "ending_type": node.ending_type if node.is_ending else "",
        "ending_title": node.ending_title if node.is_ending else "",
        "ending_description": node.ending_description if node.is_ending else "",
        "ending_closing": node.ending_closing if node.is_ending else "",
        "waiting_for": s.waiting_for,
        "mook_active_role": node.mook_active_role,
    }


# ── 1. 游戏生命周期 ──

class CreateRequest(BaseModel):
    story_id: str = "huatangchun"
    protagonist_role: str = ""  # 可选：指定主角角色，"peirong" 自动路由到裴容视角

# 角色 → 剧本的映射
ROLE_STORY_MAP = {
    "peirong": "huatangchun_peirong",
    "wentang": "huatangchun_wentang",
    "mook": "huatangchun_mook",
}

@app.post("/api/games/create")
def create_game(req: CreateRequest):
    # 如果指定了主角角色，优先按角色路由到对应剧本
    story_id = req.story_id
    if req.protagonist_role and req.protagonist_role in ROLE_STORY_MAP:
        story_id = ROLE_STORY_MAP[req.protagonist_role]
    if story_id not in STORIES:
        raise HTTPException(404, "故事不存在")
    story = STORIES[story_id]
    s = GameSession(story_id=story_id)
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
async def start_game(game_id: str, viewer_role: str = ""):
    s = get_session(game_id)
    story = STORIES[s.story_id]
    # Bot 补位：未选的角色都由 Bot 扮演
    all_roles = [r.role_id for r in story.meta.roles]
    s.bot_roles = [r for r in all_roles if r not in s.player_roles.values()]
    # 初始化亲密度变量
    for role in all_roles:
        s.variables[f"wentang_{role}"] = 0
    s.status = GameStatus.PLAYING
    # 设置 waiting_for（第一个加入的玩家，或温棠玩家）
    wentang_user = next((u for u, r in s.player_roles.items() if r == "wentang"), None)
    s.waiting_for = wentang_user or list(s.player_roles.keys())[0] if s.player_roles else "bot"
    # 给每个玩家广播各自视角
    for uid, role_id in s.player_roles.items():
        node_data = node_to_dict(game_id, viewer_role=role_id)
        await send_to_user(game_id, uid, "game_start", node_data)
    return {"status": "playing", **node_to_dict(game_id, viewer_role=viewer_role)}


@app.get("/api/games/{game_id}")
def get_game(game_id: str):
    s = get_session(game_id)
    story = STORIES[s.story_id]
    roles = [{"role_id": r.role_id, "name": r.name, "identity": r.identity, "personality": r.personality} for r in story.meta.roles]
    return {**s.model_dump(), "current_node": node_to_dict(game_id), "roles": roles, "story_roles": roles}


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

    # 无选项节点（过渡/旁白）：通过 routes 自动推进
    if len(visible) == 0:
        save_snapshot(s)
        resolved = resolve_next_node(node, s)
        if not resolved:
            raise HTTPException(400, "当前节点无选项且无路由，无法推进")
        s.current_node_id = resolved
        s.history.append({"type": "continue", "user_id": req.user_id})
        final_node = story.nodes.get(resolved)
        if final_node and final_node.is_ending:
            s.status = GameStatus.FINISHED
            result = build_result(game_id)
            await broadcast(game_id, "game_end", result)
            return {"status": "finished", "result": result}
        await broadcast(game_id, "node_update", node_to_dict(game_id))
        return node_to_dict(game_id)

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
    await broadcast_node_per_role(game_id, "node_update")
    # 状态变化广播
    await broadcast(game_id, "state_change", {
        "changes": choice.changes,
        "val": s.val,
        "flags": s.flags,
        "variables": s.variables,
        "influence_hint": choice.influence_hint,
    })
    return node_to_dict(game_id)


# ── MOOK 双人模式：一方做选择，实时广播给另一方 ──

class MookChooseRequest(BaseModel):
    user_id: str        # 做选择的玩家 user_id
    role_id: str        # 做选择的角色（wentang / peirong）
    choice_index: int

@app.post("/api/games/{game_id}/mook-choose")
async def mook_choose(game_id: str, req: MookChooseRequest):
    s = get_session(game_id)
    if s.status != GameStatus.PLAYING:
        raise HTTPException(400, "游戏未在进行中")
    story = STORIES[s.story_id]
    node = story.nodes[s.current_node_id]

    # 校验：当前节点应由该角色做选择
    if node.mook_active_role and node.mook_active_role != req.role_id:
        raise HTTPException(400, f"当前轮到 {node.mook_active_role}，不是 {req.role_id}")

    # 获取有效选项
    visible = [c for c in node.choices if evaluate_condition(c.condition, s)]

    # ── 旁白/过渡节点（无选项）：直接走 routes 推进，不需要选项索引 ──
    if len(visible) == 0:
        save_snapshot(s)
        role = next((r for r in story.meta.roles if r.role_id == req.role_id), None)
        role_name = role.name if role else req.role_id
        s.history.append({"type": "mook_continue", "user_id": req.user_id, "role_id": req.role_id})
        resolved = resolve_next_node(node, s)
        if not resolved:
            raise HTTPException(400, "当前节点无选项且无路由，无法推进")
        s.current_node_id = resolved
        final_node = story.nodes.get(resolved)
        if final_node and final_node.is_ending:
            s.status = GameStatus.FINISHED
            result = build_result(game_id)
            await broadcast(game_id, "game_end", result)
            return {"status": "finished", "result": result}
        next_n = story.nodes[s.current_node_id]
        s.waiting_for = next_n.mook_active_role or ""
        node_data = node_to_dict(game_id)
        await broadcast(game_id, "node_update", node_data)
        return node_data

    if req.choice_index >= len(visible):
        raise HTTPException(400, "选项不存在")
    choice = visible[req.choice_index]

    # 保存快照
    save_snapshot(s)
    # 应用变化
    apply_changes(choice.changes, s)

    # 记录历史
    role = next((r for r in story.meta.roles if r.role_id == req.role_id), None)
    role_name = role.name if role else req.role_id
    s.history.append({
        "type": "mook_choice",
        "user_id": req.user_id,
        "role_id": req.role_id,
        "role_name": role_name,
        "text": choice.text,
        "changes": choice.changes,
    })

    # 广播「玩家行动」事件给双方（跨屏同步）
    await broadcast(game_id, "player_action", {
        "role_id": req.role_id,
        "role_name": role_name,
        "choice_text": choice.text,
        "influence_hint": choice.influence_hint,
        "changes": choice.changes,
        "val": s.val,
        "variables": s.variables,
    })

    # 跳转节点
    next_node = story.nodes.get(choice.next)
    if not next_node:
        raise HTTPException(500, f"节点 {choice.next} 不存在")
    s.current_node_id = choice.next

    # 结局检测
    if next_node.is_ending:
        s.status = GameStatus.FINISHED
        result = build_result(game_id)
        await broadcast(game_id, "game_end", result)
        return {"status": "finished", "result": result}

    # 通过 routes 自动路由
    resolved = resolve_next_node(next_node, s)
    if resolved:
        s.current_node_id = resolved
        final_node = story.nodes.get(resolved)
        if final_node and final_node.is_ending:
            s.status = GameStatus.FINISHED
            result = build_result(game_id)
            await broadcast(game_id, "game_end", result)
            return {"status": "finished", "result": result}

    # 更新 waiting_for：下一个节点该哪个角色行动
    next_n = story.nodes[s.current_node_id]
    s.waiting_for = next_n.mook_active_role or ""

    # 广播新节点给双方
    node_data = node_to_dict(game_id)
    await broadcast(game_id, "node_update", node_data)
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
    reply_data = {
        "speaker": role.name if role else role_id,
        "speaker_type": "player",
        "text": req.text,
        "emotion_tag": "",
    }
    await broadcast(game_id, "message", reply_data)
    # 判断是否需要AI回复：如果所有其他角色都有真人玩家，不自动AI回复
    # 只有当存在bot角色时，才用AI回复
    if s.bot_roles:
        ai_reply = await generate_ai_reply(s, story, role_id, req.text)
        bot_reply = {
            "speaker": ai_reply["speaker"],
            "speaker_type": "bot",
            "text": ai_reply["text"],
            "emotion_tag": ai_reply.get("emotion", ""),
        }
        s.history.append({"type": "ai_reply", **bot_reply})
        await broadcast(game_id, "message", bot_reply)
        return {"user_message": reply_data, "ai_reply": bot_reply, "free_count_remaining": 5 - s.free_count_used}
    else:
        return {"user_message": reply_data, "ai_reply": None, "free_count_remaining": 5 - s.free_count_used}


class RollbackRequest(BaseModel):
    steps: int = 1

@app.post("/api/games/{game_id}/rollback")
async def do_rollback(game_id: str, req: RollbackRequest):
    s = get_session(game_id)
    ok = rollback(s, req.steps)
    if not ok:
        raise HTTPException(400, "没有可回溯的记录")
    await broadcast_node_per_role(game_id, "node_update")
    return node_to_dict(game_id)


@app.post("/api/games/{game_id}/finish")
def finish_game(game_id: str):
    s = get_session(game_id)
    s.status = GameStatus.FINISHED
    return build_result(game_id)


# ── 结局 AI 生成 ──

@app.post("/api/games/{game_id}/ending/generate")
async def generate_ending(game_id: str):
    """基于玩家实际路径，用 AI 生成个性化结局文本（增强 description + closing + highlights + 关系总结）"""
    s = get_session(game_id)
    story = STORIES[s.story_id]
    node = story.nodes[s.current_node_id]

    # 构建玩家路径摘要
    choice_history = [h for h in s.history if h.get("type") == "choice"]
    choice_summary = "\n".join(
        f"- {h['text']}" for h in choice_history
    ) or "（无记录）"

    # 高光时刻（改变量 >= 10 的选择）
    highlights = []
    for h in choice_history:
        changes = h.get("changes", {})
        if any(abs(v) >= 10 for v in changes.values() if isinstance(v, int)):
            highlights.append(h["text"])

    # 自由对话摘要
    free_dialogs = [h for h in s.history if h.get("type") in ("free", "ai_reply")]
    free_summary = "\n".join(
        f"  {h.get('role','?')}说：{h.get('text','')}" for h in free_dialogs[-8:]
    ) if free_dialogs else "（无自由对话）"

    # 关系数值
    rel = {k.replace("wentang_", ""): v for k, v in s.variables.items() if k.startswith("wentang_")}
    rel_text = "、".join(f"{k}好感度{v}" for k, v in rel.items()) if rel else "（无关系数据）"

    # 已解锁的 flags
    flags_text = "、".join(s.flags) if s.flags else "（无）"

    ending_type = node.ending_type if node.is_ending else "未完成"
    ending_title = node.ending_title if node.is_ending else ""
    # 静态预写文本作为参考基底
    base_desc = node.ending_description if node.is_ending else ""
    base_closing = node.ending_closing if node.is_ending else ""

    # 获取角色信息（双人模式取两位）
    role_name_map = {"wentang": "温棠", "peirong": "裴容", "peiyan": "裴琰", "peiyu": "裴瑜"}
    player_names = []
    for uid, rid in s.player_roles.items():
        rname = role_name_map.get(rid) or next((r.name for r in story.meta.roles if r.role_id == rid), rid)
        player_names.append(rname)
    players_desc = "与".join(player_names) if player_names else "玩家"

    player_role_id = next(iter(s.player_roles.values()), "wentang") if s.player_roles else "wentang"
    player_role = next((r for r in story.meta.roles if r.role_id == player_role_id), None)
    player_name = player_role.name if player_role else "你"

    system_prompt = f"""你是《{story.meta.title}》的叙事者，正在为双人玩家生成专属结局卡片文案。

故事背景：{story.meta.world_setting}
本局玩家：{players_desc}
结局类型：{ending_type} — {ending_title}

你的任务：根据两位玩家真实的游戏路径，生成有温度的专属结局文案。

写作规范：
1. duo_story（开场叙事）：100字以内的第三人称叙述，用"他们"指代两位玩家，把真实发生的2-3个关键选择或对话细节编织成一段感人的故事回顾。必须引用实际发生的选择内容，不可虚构。结尾一句话点出这段缘分的意义。
2. description（结局事件叙述）：100字以内，融入关键选择，让玩家感受到"我的选择造就了这个结局"
3. closing（余韵收束语）：40字以内，情绪层，给玩家留下回味的空间
4. highlights：从玩家路径中提炼2-3个最关键的"命运转折时刻"，每条15字以内
5. relationship_summary：一句话金句，总结这段共同经历的情感走向，适合截图分享

参考基底（可化用，不要照抄）：
description基底：{base_desc}
closing基底：{base_closing}

请严格按以下 JSON 格式返回，不要有其他内容：
{{
  "duo_story": "...",
  "description": "...",
  "closing": "...",
  "highlights": ["...", "...", "..."],
  "relationship_summary": "..."
}}"""

    user_prompt = f"""玩家的游戏路径记录：

【做出的选择（共{len(choice_history)}次）】
{choice_summary}

【自由对话片段】
{free_summary}

【关系数值】
{rel_text}

【解锁事件】
{flags_text}"""

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 800,
                    "temperature": 0.85,
                    "response_format": {"type": "json_object"},
                },
            )
            data = r.json()
            raw = data["choices"][0]["message"]["content"].strip()
            ai_result = json.loads(raw)
    except Exception:
        traceback.print_exc()
        # 降级：返回静态文本
        ai_result = {
            "duo_story": "",
            "description": base_desc,
            "closing": base_closing,
            "highlights": highlights[:3],
            "relationship_summary": rel_text,
        }

    # 组合最终结局数据
    base_result = build_result(game_id)
    return {
        **base_result,
        # AI 生成覆盖静态文本
        "duo_story": ai_result.get("duo_story", ""),
        "ending_description": ai_result.get("description", base_desc),
        "ending_closing": ai_result.get("closing", base_closing),
        "highlights": [
            {"text": t, "type": "命运转折"} for t in ai_result.get("highlights", highlights[:3])
        ],
        "relationship_summary": ai_result.get("relationship_summary", rel_text),
        "ai_generated": True,
    }


# ── 3. 故事列表 ──

@app.get("/api/stories")
def list_stories():
    seen = set()
    result = []
    for sid, s in STORIES.items():
        if s.meta.story_id in seen:
            continue
        seen.add(s.meta.story_id)
        result.append({
            "story_id": s.meta.story_id,
            "title": s.meta.title,
            "author": s.meta.author,
            "genre": s.meta.genre,
            "max_players": s.meta.max_players,
            "protagonist": next((r.name for r in s.meta.roles if r.required), ""),
        })
    return result


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
        "player_roles": s.player_roles,
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
