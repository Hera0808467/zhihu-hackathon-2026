# 《画堂春》代码改动指南

> 给队友快速上手用，改交互和prompt风格看这篇就够了。

---

## 项目结构

```
app/
├── main.py          # API路由 + AI回复生成（system prompt在这）
├── story_data.py    # 剧本数据（角色卡、节点、选项）
├── engine.py        # 剧本引擎（条件判定、状态流转，一般不用改）
├── models.py        # 数据模型定义（一般不用改）
└── zhihu_client.py  # 知乎API客户端
```

---

## 一、改角色说话风格

📁 文件：`app/story_data.py`

每个角色是一个 `RoleProfile`，关键字段：

| 字段 | 作用 | 示例 |
|------|------|------|
| `personality` | 性格描述，影响AI理解角色 | "温和隐忍，善良心软，不争不抢" |
| `speaking_style` | **说话风格，直接决定输出语气** | "语气温和，偶尔结巴，对皇帝恭敬" |
| `core_purpose` | 角色动机 | "活下去，守护孩子" |
| `weakness` | 弱点，影响角色在压力下的反应 | "心软，胆小" |

**改法：** 直接改对应角色的字符串就行。比如想让裴容更阴鸷：

```python
# 改前
speaking_style="语气平淡沉稳，带帝王威严，说话简洁偶尔反问"
# 改后
speaking_style="语气阴冷克制，喜欢用反问施压，偶尔一句话暗藏杀机"
```

---

## 二、改AI回复的System Prompt

📁 文件：`app/main.py`，第375-392行，`generate_ai_reply` 函数内

当前模板：
```python
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
```

**常见调整：**
- 改字数限制：`不超过80字` → 改成你想要的长度
- 加输出格式要求：比如要求带情绪标签、带动作描写
- 加更多约束：比如"不能主动提及某剧情线索"

---

## 三、改AI生成参数

📁 文件：`app/main.py`，第406行附近

```python
json={
    "model": LLM_MODEL,
    "messages": messages,
    "max_tokens": 150,       # 最大输出token数
    "temperature": 0.8,      # 创造性（0.0-1.0，越高越随机）
}
```

- `temperature` 调低(0.3-0.5)：回复更稳定可控，适合严肃剧情
- `temperature` 调高(0.8-1.0)：回复更有变化，适合日常闲聊
- `max_tokens`：控制回复最大长度

---

## 四、改剧情节点文本（旁白/引导）

📁 文件：`app/story_data.py`，每个 `StoryNode` 里的 `segments`

这是**固定文本**，不经过AI生成，就是剧情推进时展示的旁白和角色台词。直接改字符串。

---

## 五、改LLM模型

📁 文件：`app/main.py` 顶部

找到这几个变量：
```python
LLM_BASE_URL = "..."   # API地址
LLM_API_KEY = "..."    # API密钥
LLM_MODEL = "..."      # 模型名称
```

换模型就改这里。

---

## 快速验证

```bash
# 启动服务
cd zhihu-hackathon
source venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000

# 测试自由对话（需要先创建房间+加入+开始）
curl -X POST http://localhost:8000/game/GAME_ID/speak \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","role_id":"wentang","text":"裴琰，你今天功课做完了吗？"}'
```

---

## TL;DR

| 想改什么 | 改哪个文件 | 改什么 |
|----------|-----------|--------|
| 角色怎么说话 | `story_data.py` | RoleProfile 的 speaking_style |
| AI回复规则 | `main.py:375` | system_prompt 模板 |
| 回复长度/随机性 | `main.py:406` | max_tokens / temperature |
| 固定剧情文本 | `story_data.py` | StoryNode 的 segments |
| 换模型 | `main.py` 顶部 | LLM_BASE_URL / MODEL |
