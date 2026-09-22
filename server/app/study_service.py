from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

from .database import Database
from .learning import build_card, detect_subject, render_study_markdown
from .llm import LocalLlmClient
from .notion import NotionClient

logger = logging.getLogger(__name__)


class StudyService:
    def __init__(self, database: Database, llm: LocalLlmClient, notion: NotionClient, notes_dir: Path) -> None:
        self.database = database
        self.llm = llm
        self.notion = notion
        self.notes_dir = notes_dir

    async def finalize(self, session_id: str) -> dict[str, object]:
        session = self.database.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        transcripts = self.database.all_transcripts(session_id)
        cards = self.database.knowledge_cards(session_id)
        combined = "".join(str(row["text"]) for row in transcripts)
        subject = detect_subject(str(session["title"]), combined)

        if not cards and transcripts:
            synthetic_segments = [
                SimpleNamespace(start=row["start_seconds"], end=row["end_seconds"], text=row["text"])
                for row in transcripts
            ]
            card = build_card(str(session["title"]), synthetic_segments)
            if card:
                self.database.add_knowledge_card(session_id, card.to_dict())
                cards = self.database.knowledge_cards(session_id)

        draft = render_study_markdown(
            str(session["title"]),
            session.get("url"),
            subject.name,
            cards,
            transcripts,
        )
        markdown = draft
        llm_status = "disabled"
        if self.llm.enabled:
            try:
                markdown = await self.llm.improve_markdown(str(session["title"]), subject.name, draft)
                llm_status = "completed"
            except Exception as exc:
                llm_status = "fallback"
                logger.exception("Local LLM finalization failed; using deterministic draft: %s", exc)

        self.notes_dir.mkdir(parents=True, exist_ok=True)
        local_path = self.notes_dir / f"{session_id}.md"
        local_path.write_text(markdown, encoding="utf-8")

        already_synced = bool(session.get("notion_page_id"))
        sync_status = "completed" if already_synced else "pending" if self.notion.enabled else "not_configured"
        self.database.finish_session(session_id, subject.name, markdown, sync_status)
        if self.notion.enabled and not already_synced:
            self.database.enqueue_sync(session_id, "notion", json.dumps({"markdown": markdown}, ensure_ascii=False))
            await self.retry_notion_sync(limit=1)

        updated = self.database.get_session(session_id) or session
        return {
            "sessionId": session_id,
            "subject": subject.name,
            "markdown": markdown,
            "localPath": str(local_path),
            "cardCount": len(cards),
            "llmStatus": llm_status,
            "syncStatus": updated.get("sync_status", sync_status),
            "notionPageId": updated.get("notion_page_id"),
            "syncError": updated.get("sync_error"),
        }

    async def retry_notion_sync(self, limit: int = 10) -> dict[str, int]:
        if not self.notion.enabled:
            return {"completed": 0, "failed": 0}
        completed = 0
        failed = 0
        for job in self.database.pending_sync_jobs(limit=limit):
            self.database.set_sync_job(int(job["id"]), "running")
            try:
                payload = json.loads(str(job["payload"]))
                page = await self.notion.create_page(str(payload["markdown"]))
                self.database.set_sync_job(int(job["id"]), "completed")
                self.database.set_notion_result(str(job["session_id"]), "completed", page.id)
                completed += 1
            except Exception as exc:
                error = str(exc)[:1000]
                self.database.set_sync_job(int(job["id"]), "failed", error)
                self.database.set_notion_result(str(job["session_id"]), "failed", error=error)
                failed += 1
        return {"completed": completed, "failed": failed}
