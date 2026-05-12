"""剧本引擎：节点跳转、条件判定、状态管理"""
from __future__ import annotations
from app.models import GameSession, StoryScript, StoryNode, Choice


def evaluate_condition(condition: str, session: GameSession) -> bool:
    """评估条件表达式"""
    if not condition or condition == "default":
        return True
    c = condition.strip()
    # flag 判定
    if c.startswith("hasFlag"):
        flag = c.split("'")[1] if "'" in c else c.split(" ")[1]
        return flag in session.flags
    if c.startswith("!hasFlag"):
        flag = c.split("'")[1] if "'" in c else c.split(" ")[1]
        return flag not in session.flags
    # val 判定
    for op in [">=", "<=", "!=", "==", ">", "<"]:
        if f"val {op}" in c:
            val_str = c.split(op)[1].strip()
            target = int(val_str)
            if op == ">=": return session.val >= target
            if op == "<=": return session.val <= target
            if op == ">":  return session.val > target
            if op == "<":  return session.val < target
            if op == "==": return session.val == target
            if op == "!=": return session.val != target
    # 变量判定
    for op in [">=", "<=", "!=", "==", ">", "<"]:
        if op in c:
            parts = c.split(op)
            var_name = parts[0].strip()
            val = int(parts[1].strip())
            cur = session.variables.get(var_name, 0)
            if op == ">=": return cur >= val
            if op == "<=": return cur <= val
            if op == ">":  return cur > val
            if op == "<":  return cur < val
            if op == "==": return cur == val
            if op == "!=": return cur != val
    return True


def apply_changes(changes: dict, session: GameSession):
    """应用选择带来的变化"""
    if "val" in changes:
        session.val = max(0, min(100, session.val + changes["val"]))
    if "valSet" in changes:
        session.val = max(0, min(100, changes["valSet"]))
    if "addFlag" in changes:
        f = changes["addFlag"]
        if f not in session.flags:
            session.flags.append(f)
    if "addFlags" in changes:
        for f in changes["addFlags"]:
            if f not in session.flags:
                session.flags.append(f)
    if "removeFlag" in changes:
        f = changes["removeFlag"]
        if f in session.flags:
            session.flags.remove(f)
    if "set" in changes:
        for k, v in changes["set"].items():
            session.variables[k] = v
    # 亲密度变化（自定义）
    for key in changes:
        if key.endswith("_affinity"):
            role = key.replace("_affinity", "")
            session.variables[role] = session.variables.get(role, 0) + changes[key]


def resolve_next_node(node: StoryNode, session: GameSession) -> str | None:
    """通过 routes 自动路由解析下一个节点"""
    for route in node.routes:
        if evaluate_condition(route.condition, session):
            return route.next
    return None


def save_snapshot(session: GameSession):
    """保存快照用于回溯"""
    snap = {
        "current_node_id": session.current_node_id,
        "val": session.val,
        "flags": session.flags.copy(),
        "variables": session.variables.copy(),
        "history_len": len(session.history),
    }
    session.snapshots.append(snap)
    # 最多保留 5 个快照
    if len(session.snapshots) > 5:
        session.snapshots.pop(0)


def rollback(session: GameSession, steps: int = 1) -> bool:
    """回溯到之前的状态"""
    steps = min(steps, 3, len(session.snapshots))
    if steps == 0:
        return False
    for _ in range(steps):
        snap = session.snapshots.pop()
    session.current_node_id = snap["current_node_id"]
    session.val = snap["val"]
    session.flags = snap["flags"]
    session.variables = snap["variables"]
    session.history = session.history[:snap["history_len"]]
    return True
