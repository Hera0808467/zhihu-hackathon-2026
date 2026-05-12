"""知乎开放平台 API 客户端"""
import hmac, hashlib, base64, time
import httpx

BASE_URL = "https://openapi.zhihu.com"

# 圈子 ID
RINGS = {
    "openclaw": "2001009660925334090",
    "a2a": "2015023739549529606",
    "hackathon": "2029619126742656657",
}


class ZhihuClient:
    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self._client = httpx.AsyncClient(base_url=BASE_URL, timeout=15)

    def _make_headers(self) -> dict:
        ts = str(int(time.time()))
        log_id = f"req_{int(time.time() * 1000)}"
        extra_info = ""
        sign_str = f"app_key:{self.app_key}|ts:{ts}|logid:{log_id}|extra_info:{extra_info}"
        h = hmac.new(self.app_secret.encode(), sign_str.encode(), hashlib.sha256)
        sign = base64.b64encode(h.digest()).decode()
        return {
            "X-App-Key": self.app_key,
            "X-Timestamp": ts,
            "X-Log-Id": log_id,
            "X-Sign": sign,
            "X-Extra-Info": extra_info,
        }

    # ── 圈子 API ──

    async def get_ring_detail(self, ring_id: str = RINGS["hackathon"]) -> dict:
        r = await self._client.get(f"/openapi/ring/detail?ring_id={ring_id}", headers=self._make_headers())
        return r.json()

    async def publish_pin(self, ring_id: str, content: str) -> dict:
        r = await self._client.post(
            "/openapi/publish/pin",
            headers=self._make_headers(),
            json={"ring_id": ring_id, "content": content},
        )
        return r.json()

    async def get_comments(self, content_token: str, cursor: str = "", limit: int = 20) -> dict:
        r = await self._client.get(
            f"/openapi/comment/list?content_token={content_token}&cursor={cursor}&limit={limit}",
            headers=self._make_headers(),
        )
        return r.json()

    async def create_comment(self, content_token: str, content: str, reply_to: str = "") -> dict:
        body = {"content_token": content_token, "content": content}
        if reply_to:
            body["reply_comment_id"] = reply_to
        r = await self._client.post("/openapi/comment/create", headers=self._make_headers(), json=body)
        return r.json()

    async def react(self, content_token: str, reaction: str = "upvote") -> dict:
        r = await self._client.post(
            "/openapi/reaction",
            headers=self._make_headers(),
            json={"content_token": content_token, "reaction": reaction},
        )
        return r.json()

    # ── 故事 API（路径待确认） ──

    async def get_story_list(self) -> dict:
        """获取故事列表 - 路径待从文档确认"""
        # TODO: 确认正确路径
        for path in ["/openapi/hackathon/story_list", "/openapi/story/list", "/community/story_list"]:
            r = await self._client.get(path, headers=self._make_headers())
            if r.status_code == 200:
                return r.json()
        return {"status": 1, "msg": "故事列表接口路径未找到"}

    async def get_story_detail(self, story_id: str) -> dict:
        """获取故事详情 - 路径待确认"""
        for path in [f"/openapi/hackathon/story/{story_id}", f"/openapi/story/{story_id}"]:
            r = await self._client.get(path, headers=self._make_headers())
            if r.status_code == 200:
                return r.json()
        return {"status": 1, "msg": "故事详情接口路径未找到"}
