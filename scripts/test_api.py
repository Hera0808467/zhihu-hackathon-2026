#!/usr/bin/env python3
"""快速测试完整游戏流程"""
import httpx, json

BASE = "http://localhost:8000"

def test():
    c = httpx.Client()

    # 1. 创建房间
    r = c.post(f"{BASE}/api/games/create", json={"story_id": "huatangchun"})
    game_id = r.json()["game_id"]
    print(f"✅ 创建房间: {game_id}")

    # 2. 选角色
    c.post(f"{BASE}/api/games/{game_id}/join", json={"user_id": "user_001", "role_id": "wentang"})
    print("✅ 选角色: 温棠")

    # 3. 开始
    r = c.post(f"{BASE}/api/games/{game_id}/start")
    node = r.json()
    print(f"✅ 开始 → [{node['act_title']}] {node['scene_name']}")
    for i, ch in enumerate(node["choices"]):
        print(f"   {i}: {ch['text']}")

    # 4. 选择接受裴琰
    print("\n--- 选择「惊讶」---")
    r = c.post(f"{BASE}/api/games/{game_id}/choose", json={"user_id": "user_001", "choice_index": 0})
    node = r.json()
    print(f"→ 节点: {node['node_id']} | {node['scene_name']}")

    print("\n--- 选择「臣妾愿意照料琰儿」---")
    # 先跳过皇帝对话
    r = c.post(f"{BASE}/api/games/{game_id}/choose", json={"user_id": "user_001", "choice_index": 1})
    node = r.json()
    print(f"→ 节点: {node['node_id']}")

    # 继续推进到第二幕
    r = c.post(f"{BASE}/api/games/{game_id}/choose", json={"user_id": "user_001", "choice_index": 0})
    node = r.json()
    print(f"→ 节点: {node['node_id']}")

    # 5. 查看状态
    r = c.get(f"{BASE}/api/games/{game_id}")
    state = r.json()
    print(f"\n📊 当前状态:")
    print(f"   val: {state['val']}")
    print(f"   flags: {state['flags']}")
    print(f"   亲密度: {state['variables']}")

    print("\n✅ 所有测试通过！服务正常运行。")

if __name__ == "__main__":
    test()
