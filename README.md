# 画堂春互动文游 · 后端

> 知乎 Hackathon 2026 · 盐选小说沉浸式角色互动文游

## 快速启动

```bash
cd zhihu-hackathon
source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API 文档：http://localhost:8000/docs

## 核心 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/games/create | 创建房间 |
| POST | /api/games/{id}/join | 选角色加入 |
| POST | /api/games/{id}/start | 开始游戏（Bot补位） |
| POST | /api/games/{id}/choose | 做选择（guided模式） |
| POST | /api/games/{id}/speak | 自由发言（free模式，限5次） |
| POST | /api/games/{id}/rollback | 回溯（最多3步） |
| POST | /api/games/{id}/finish | 生成结局报告 |
| GET  | /api/games/{id} | 获取游戏状态 |
| WS   | /ws/games/{id} | WebSocket 实时推送 |

## 当前进度

- [x] 数据模型（models.py）
- [x] 剧本引擎（engine.py）
- [x] 《画堂春》完整剧本（story_data.py）：3幕20节点3结局
- [x] FastAPI 后端（main.py）
- [x] WebSocket 实时推送
- [ ] 接入知乎直答 API（free 模式 AI 回复）
- [ ] 前端页面

## 文件结构

```
zhihu-hackathon/
├── app/
│   ├── main.py          # FastAPI 应用
│   ├── models.py        # 数据模型
│   ├── engine.py        # 剧本引擎
│   └── story_data.py    # 《画堂春》剧本
├── scripts/
│   └── test_api.py      # 快速测试
├── venv/                # Python 虚拟环境
└── README.md
```

## TODO

1. **接入知乎直答 API**：在 `main.py` 的 `generate_ai_reply` 函数中接入
2. **前端**：对接 /api/games 和 WebSocket
3. **OAuth 登录**：接入知乎 OAuth，替换 mock user_id
