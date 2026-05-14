# 🎭 画堂春 · 沉浸式多人 AI 互动文游

> *"一卷画堂春，半阙血色词。每一次选择，都改写命运。"*

---

## 📋 项目概览

| 维度 | 内容 |
|------|------|
| 项目名称 | 画堂春 · 盐选互动文游 |
| 赛道 | 知乎 Hackathon 2026 · 引力场 |
| 核心定位 | 基于知乎盐选 IP 的 **多人实时 AI 互动文字冒险** |
| 技术亮点 | 多视角剧本引擎 × WebSocket 实时同步 × LLM 角色扮演 × 双人 MOOK 模式 |

---

## 🌟 产品创新点

### 1. 从"读"到"活"——盐选 IP 的全新打开方式

传统网文是单向阅读。我们将知乎盐选长篇小说《画堂春》转化为 **多人可交互的实时文字冒险**：

- 📖 保留原著文学质感，AI 不是替代作者，而是**延展故事的可能性**
- 🎭 玩家自由代入任意角色，获得**专属视角**的叙事体验
- 🤝 支持 2-5 人同时在线，各自扮演不同角色，**共同推动剧情**

### 2. 三种沉浸模式

| 模式 | 描述 | 体验差异 |
|------|------|---------|
| **温棠线** | 扮演女主，从底层妃嫔视角看宫斗 | 被动中求生存，暖心养成 |
| **裴容线** | 扮演帝王，在权谋中寻找真情 | 俯视视角，决策压力 |
| **双人 MOOK** | 温棠 × 裴容双视角交叉叙事 | 轮流选择，命运交织，看到对方看不到的秘密 |

### 3. "选择"不只是分支——而是人格映射

通过知乎 OAuth 获取用户发文风格 → AI 生成专属人设标签 → 融入角色行为模式。**你的知乎人格，决定了你在故事里的命运。**

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端层 (Frontend)                        │
│  React 19 + TanStack Router/Start + Tailwind CSS + Radix UI     │
│  部署: Cloudflare Workers (SSR + Edge Runtime)                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTPS / WSS
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                        服务端层 (Backend)                         │
│  FastAPI + Uvicorn (Async) + WebSocket 双向通信                   │
├─────────────┬───────────────┬───────────────┬───────────────────┤
│  剧本引擎    │  AI 对话生成   │  房间管理      │  知乎 OAuth       │
│  状态机+条件  │  LLM 角色扮演  │  实时广播      │  人格融合         │
└─────────────┴───────────────┴───────────────┴───────────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ 剧本数据  │ │ LLM API  │ │知乎 OpenAPI│
        │ 23节点×3  │ │ GPT-5.5  │ │ OAuth2.0  │
        │ 3种结局   │ │ 角色一致性 │ │ 用户画像   │
        └──────────┘ └──────────┘ └──────────┘
```

---

## 🔧 核心技术实现

### 1. 多视角剧本引擎

```python
# 同一个故事节点，不同角色看到不同的叙事
STORIES = {
    "huatangchun_wentang": HUATANGCHUN_WENTANG,   # 温棠视角：23节点
    "huatangchun_peirong": HUATANGCHUN_PEIRONG,   # 裴容视角：23节点
    "huatangchun_mook": HUATANGCHUN_MOOK,         # 双人交叉：22节点
}
```

**设计哲学**：不是简单的"选项A/B"分支树，而是：
- **条件路由**：根据亲密度、标志位、历史选择动态解锁路径
- **角色分段**：`role_segments` 让同一场景下不同角色看到不同内心戏
- **影响力系统**：每次选择影响多个角色的亲密度，最终决定 3 种结局走向

### 2. MOOK 双人实时交互协议

```
Player A (温棠)                    Server                    Player B (裴容)
      │                              │                              │
      │──── create + join ──────────►│                              │
      │◄─── room_id + invite_link ──│                              │
      │                              │◄──── join (via link) ───────│
      │                              │──── start_game ────────────►│
      │◄──── game_start (WS) ───────│                              │
      │                              │                              │
      │  [mook_active_role: wentang]  │                              │
      │──── mook-choose(idx=1) ────►│                              │
      │                              │──── player_action (WS) ────►│
      │                              │──── node_update (WS) ──────►│
      │◄──── node_update (WS) ──────│                              │
      │                              │                              │
      │  [mook_active_role: peirong]  │                              │
      │                              │◄──── mook-choose(idx=0) ───│
      │◄──── player_action (WS) ────│                              │
      │◄──── node_update (WS) ──────│                              │
      │                              │──── node_update (WS) ──────►│
      │                              │                              │
      │         ... 轮流交替直到结局 ...                              │
      │                              │                              │
      │◄──── game_end (WS) ────────│──── game_end (WS) ─────────►│
```

**核心机制**：
- `mook_active_role` 控制当前轮到谁操作
- 非活跃方看到"等待对方操作中…"
- 每次选择实时广播 `player_action` 事件，双方同步看到对方的决策

### 3. AI 角色扮演引擎

```python
system_prompt = f"""你是《画堂春》中的{bot_role.name}。
身份：{bot_role.identity}
性格：{bot_role.personality}
说话风格：{bot_role.speaking_style}
核心目的：{bot_role.core_purpose}
弱点：{bot_role.weakness}

规则：
- 严格保持角色一致性
- 回复简短有力，不超过80字
- 根据对方的话调整情绪和态度"""
```

**AI 不是万能的叙述者，而是有性格、有弱点、有目的的"演员"。**

- 6 个角色各有独立人设 prompt（身份/性格/说话风格/核心目的/弱点）
- 对话历史窗口保持上下文连贯
- Bot 补位：未选角色由 AI 自动扮演，保持对话流畅性

### 4. 前端实时架构

```typescript
// 游戏状态管理 — 单一 Hook 驱动全流程
const {
  phase,        // idle → creating → joined → playing → ended
  messages,     // 统一消息流（旁白/对话/选择/奖励/通知）
  currentNode,  // 当前剧情节点
  result,       // 结局数据
  makeChoice,   // 做选择
  sendMessage,  // 自由对话
} = useGame(myRole, gameMode);
```

**设计亮点**：
- **SSR + Client Hydration**：首屏 SSR 加速，交互部分纯客户端
- **消息去重**：WebSocket 广播 + 本地 optimistic update，通过 role 判断避免重复
- **渐进式渲染**：剧本 segments 逐条动画展示，模拟"翻书"节奏感

---

## 📊 技术指标

| 指标 | 数值 |
|------|------|
| 剧本总节点数 | 68 (23×2单人 + 22双人) |
| 可达结局数 | 9 (3×3模式) |
| WebSocket 消息延迟 | < 200ms (同区域) |
| 首屏加载 | < 1.5s (Cloudflare Edge) |
| AI 回复延迟 | 1-3s (GPT-5.5) |
| 并发房间支持 | 100+ (单实例) |

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | React 19 + TanStack Start + Vite 7 |
| UI 组件 | Radix UI + Tailwind CSS 4 + shadcn/ui |
| 前端部署 | Cloudflare Workers (Edge SSR) |
| 后端框架 | Python FastAPI + Uvicorn (Async) |
| 实时通信 | WebSocket (原生) |
| AI 模型 | GPT-5.5 via OpenAI-compatible API |
| 认证 | 知乎 OAuth 2.0 |
| 部署 | Cloudflare Tunnel / Workers |

---

## 🗂️ API 设计

### RESTful 接口

| Method | Path | 功能 |
|--------|------|------|
| POST | `/api/games/create` | 创建房间（支持 protagonist_role 视角选择） |
| POST | `/api/games/{id}/join` | 加入房间 + 选择角色 |
| POST | `/api/games/{id}/start` | 开始游戏（Bot 补位） |
| GET | `/api/games/{id}` | 获取房间完整状态 |
| POST | `/api/games/{id}/choose` | 单人模式做选择 |
| POST | `/api/games/{id}/mook-choose` | 双人模式轮流选择 |
| POST | `/api/games/{id}/speak` | 自由对话（触发 AI 回复） |
| POST | `/api/games/{id}/rollback` | 剧情回溯 |
| POST | `/api/games/{id}/finish` | 强制结束 + 生成结局报告 |

### WebSocket 事件

| 事件 | 方向 | 描述 |
|------|------|------|
| `connected` | S→C | 连接成功，返回当前节点 |
| `game_start` | S→C | 游戏开始（双人模式） |
| `node_update` | S→C | 剧情推进，新节点数据 |
| `player_action` | S→C | 对方做了选择（双人同步） |
| `message` | S→C | 实时对话消息 |
| `state_change` | S→C | 状态变化（亲密度/标志位） |
| `game_end` | S→C | 游戏结束，结局数据 |

---

## 🎯 与知乎生态的结合

1. **盐选 IP 变现新路径**：从付费阅读 → 付费互动体验
2. **OAuth 人格融合**：用户的知乎发文风格影响游戏内角色行为
3. **社交裂变**：双人模式邀请链接 + 结局分享卡片 → 站内传播
4. **创作者经济**：未来支持 UGC 剧本上传，盐选作者变身游戏设计师

---

## 👥 团队分工

| 成员 | 职责 |
|------|------|
| Huan | 产品设计 · 前后端联调 · 项目管理 |
| 前端同学 | UI 设计 · React 组件 · Cloudflare 部署 |
| AI 虾虾酱 | 后端架构 · 剧本引擎 · API 联调 · 部署 |

---

## 🚀 未来规划

- **Phase 2**：支持 UGC 剧本创作工具（可视化节点编辑器）
- **Phase 3**：接入知乎圈子，形成"剧本杀社区"
- **Phase 4**：语音交互 + TTS 角色配音
- **Phase 5**：AI 实时生成无限剧情（不再依赖预设节点）

---

> *"同一卷《画堂春》，没有两场相同的结局。"*
