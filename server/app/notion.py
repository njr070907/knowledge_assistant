from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class NotionPage:
    id: str
    url: str | None


class NotionClient:
    API_ROOT = "https://api.notion.com/v1"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.notion_token and self.settings.notion_parent_page_id)

    @property
    def status(self) -> dict[str, object]:
        return {
            "configured": self.enabled,
            "parentPageConfigured": bool(self.settings.notion_parent_page_id),
        }

    def _create_page_sync(self, markdown: str) -> NotionPage:
        payload = {
            "parent": {
                "type": "page_id",
                "page_id": self.settings.notion_parent_page_id,
            },
            "markdown": markdown,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.notion_token}",
            "Notion-Version": self.settings.notion_api_version,
            "Content-Type": "application/json",
        }

        for attempt in range(3):
            request = urllib.request.Request(
                f"{self.API_ROOT}/pages",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    body = json.load(response)
                return NotionPage(id=str(body["id"]), url=body.get("url"))
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt == 2:
                    detail = exc.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"Notion API {exc.code}: {detail[:500]}") from exc
                delay = float(exc.headers.get("Retry-After", "1"))
                time.sleep(max(1.0, min(delay, 60.0)))
        raise RuntimeError("Notion 同步重试次数已用尽")

    async def create_page(self, markdown: str) -> NotionPage:
        if not self.enabled:
            raise RuntimeError("Notion 尚未配置")
        return await asyncio.to_thread(self._create_page_sync, markdown)

