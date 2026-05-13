# 画堂春 · 沉浸式多人互动文游

> 基于知乎盐选小说《画堂春》，将经典古言故事转化为多人实时互动的角色扮演文字冒险游戏。

## ✨ 核心特色

- **多人实时互动** — 2-5人同时在线，各自扮演不同角色，共同推动剧情
- **MOOK双人模式** — 两位玩家同屏对话，轮流做选择，共同经历同一场剧情
- **双视角叙事** — 不同角色看到不同的旁白、内心戏和选择，体验截然不同的故事
- **AI智能补位** — 没有真人的角色由AI扮演，保持对话自然流畅
- **分支结局** — 3幕20+节点3种结局，玩家选择决定故事走向
- **自由对话** — 在剧情推进之外，可以用角色身份自由交流
- **社交分享卡片** — 结局页AI生成专属高光回顾，涵盖共同经历、高光选择、名言金句

## 🎭 角色

| 角色 | 身份 | 定位 |
|------|------|------|
| **温棠** | 温贵人，四皇子生母 | 主角，推动剧情 |
| **裴琰** | 三皇子，9岁 | 主角，情感核心 |
| **裴容** | 大胤皇帝 | 配角，权力中心 |
| **裴瑜** | 四皇子，6岁 | 配角，冲突制造 |
| **舒贵妃** | 后宫实权人物 | 配角，对抗力量 |

## 🏗️ 技术架构

```
┌─────────────┐     WebSocket      ┌──────────────┐
│  前端 (HTML) │◄──────────────────►│  FastAPI 后端 │
│  移动端适配   │    实时双向通信      │  异步处理     │
└─────────────┘                    └──────┬───────┘
                                          │
                              ┌────────────┼────────────┐
                              ▼            ▼            ▼
                        剧本引擎      AI对话生成    知乎API
                      (状态机+条件)  (LLM角色扮演)  (圈子/直答)
```

**技术栈：**
- 后端：Python FastAPI + WebSocket + Pydantic
- 前端：原生HTML/CSS/JS，移动端优先
- AI：兼容OpenAI格式的LLM API（角色扮演对话生成 + AI结局生成）
- 部署：Cloudflare Tunnel / 任意云服务器

## 🚀 快速开始

### 本地运行

```bash
# 1. 克隆
git clone https://github.com/Hera0808467/zhihu-hackathon-2026.git
cd zhihu-hackathon-2026

# 2. 安装依赖
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置LLM（可选，不配也能玩，AI回复会fallback）
export LLM_BASE_URL="https://your-llm-api.com/v1"
export LLM_API_KEY="your-key"
export LLM_MODEL="your-model"

# 4. 启动
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5. 打开浏览器
open http://localhost:8000
```

### 公网部署（手机体验）

```bash
# 方式1：Cloudflare Tunnel（免费，临时）
cloudflared tunnel --url http://localhost:8000

# 方式2：部署到云服务器
# 确保8000端口开放，直接访问 http://your-ip:8000
```

## 🎮 游戏流程

### 单人 / 多人房间模式
1. **玩家A** 打开链接 → 点「进入世界」→ 获得房间号 → 选择角色（温棠或裴容）
2. **玩家A** 把房间号发给朋友
3. **玩家B** 打开链接 → 输入房间号 → 选择剩余角色
4. 双方点「开始游戏」→ 各自看到自己视角的剧情
5. 做出选择 / 自由对话 → 剧情实时推进
6. 到达三种结局之一，查看 AI 生成的个人化结局分享卡

### MOOK 双人对话模式
1. 点「双人对话」→ 两位玩家分别扮演温棠和裴容
2. 同一页面左右分栏，轮流做选择，实时同步
3. 结局触发后生成共同分享卡片（含 AI 叙事、高光时刻、名言摘录）

## 📁 项目结构

```
├── app/
│   ├── main.py          # API路由 + WebSocket + AI对话/结局生成
│   ├── models.py        # 数据模型（角色/节点/会话/结局）
│   ├── engine.py        # 剧本引擎（条件判定/状态流转）
│   ├── story_data.py    # 《画堂春》完整剧本数据（含MOOK双人版）
│   └── zhihu_client.py  # 知乎开放平台API客户端
├── static/
│   └── index.html       # 前端页面（单文件，含双人模式UI）
├── requirements.txt     # Python依赖
├── DEV_GUIDE.md         # 开发者改动指南
└── README.md
```

## 🔌 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/games/create` | 创建游戏房间 |
| POST | `/api/games/{id}/join` | 加入房间选择角色 |
| POST | `/api/games/{id}/start` | 开始游戏，返回首节点 |
| GET  | `/api/games/{id}` | 获取房间状态 |
| POST | `/api/games/{id}/choose` | 单人选择推进剧情 |
| POST | `/api/games/{id}/mook-choose` | MOOK双人轮流选择 |
| POST | `/api/games/{id}/speak` | 自由对话（AI角色扮演回复） |
| POST | `/api/games/{id}/finish` | 结算结局 |
| POST | `/api/games/{id}/ending/generate` | AI生成个人化结局分享卡 |
| POST | `/api/games/{id}/rollback` | 回溯到上一快照 |
| WS   | `/ws/games/{id}` | WebSocket实时推送（节点/对话/结局） |

## 🔧 开发指南

见 [DEV_GUIDE.md](./DEV_GUIDE.md) — 如何修改角色风格、System Prompt、剧情节点等。

## 📖 原作

- 小说：《画堂春》by 鸠森
- 来源：知乎盐选专栏
- 类型：古言 · 宫斗 · 救赎 · HE

## 🏆 知乎黑客松 2026

本项目为知乎黑客松2026参赛作品，探索「盐选IP × AI互动」的新玩法。

---

**团队：** Huan · 靳周涵 · 郦星羽 · 阮庭萱 · 武子琳 · 江止
