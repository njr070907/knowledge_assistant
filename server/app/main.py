from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .database import Database
from .learning import TopicAccumulator
from .llm import LocalLlmClient
from .notion import NotionClient
from .study_service import StudyService
from .transcriber import LocalTranscriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("zhiliu")

database = Database(settings.database_path)
transcriber = LocalTranscriber(settings)
llm = LocalLlmClient(settings)
notion = NotionClient(settings)
study_service = StudyService(database, llm, notion, settings.data_dir / "notes")


class MarkRequest(BaseModel):
    kind: str = Field(pattern="^(important|confusing|recall)$")
    video_seconds: float = Field(ge=0)
    note: str | None = Field(default=None, max_length=2000)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Zhiliu Local Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "zhiliu",
        "asr": transcriber.status,
        "llm": llm.status,
        "notion": notion.status,
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, object]:
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session": session,
        "cards": database.knowledge_cards(session_id),
        "transcripts": database.recent_transcripts(session_id, limit=80),
    }


@app.post("/api/sessions/{session_id}/marks")
async def add_mark(session_id: str, request: MarkRequest) -> dict[str, object]:
    if not database.get_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    mark_id = database.add_mark(session_id, request.kind, request.video_seconds, request.note)
    return {"ok": True, "id": mark_id}


@app.post("/api/sessions/{session_id}/finalize")
async def finalize_session(session_id: str) -> dict[str, object]:
    try:
        return await study_service.finalize(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc


@app.post("/api/sync/notion/retry")
async def retry_notion_sync() -> dict[str, int]:
    return await study_service.retry_notion_sync()


@app.websocket("/ws/audio")
async def audio_stream(websocket: WebSocket, token: str) -> None:
    if len(token) < 16:
        await websocket.close(code=1008, reason="invalid session token")
        return

    await websocket.accept()
    session_id: str | None = None
    sample_rate = 16000
    chunk_bytes = int(settings.chunk_seconds * sample_rate * 2)
    received_bytes = 0
    buffer = bytearray()
    accumulator: TopicAccumulator | None = None

    try:
        first_message = await websocket.receive_text()
        metadata = json.loads(first_message)
        if metadata.get("type") != "session_start":
            await websocket.send_json({"type": "error", "message": "缺少会话信息"})
            await websocket.close(code=1008)
            return

        session_id = str(metadata.get("sessionId") or uuid.uuid4())
        sample_rate = int(metadata.get("sampleRate") or 16000)
        chunk_bytes = int(settings.chunk_seconds * sample_rate * 2)
        database.start_session(
            session_id,
            str(metadata.get("title") or "未命名视频"),
            metadata.get("url"),
            metadata.get("platform"),
        )
        accumulator = TopicAccumulator(
            str(metadata.get("title") or "未命名视频"),
            topic_seconds=settings.topic_seconds,
        )
        await websocket.send_json({"type": "ready", "sessionId": session_id})

        while True:
            packet = await websocket.receive()
            if packet.get("type") == "websocket.disconnect":
                break
            pcm = packet.get("bytes")
            if not pcm:
                continue
            buffer.extend(pcm)

            while len(buffer) >= chunk_bytes:
                chunk = bytes(buffer[:chunk_bytes])
                del buffer[:chunk_bytes]
                offset = received_bytes / (sample_rate * 2)
                received_bytes += len(chunk)
                try:
                    segments = await transcriber.transcribe(chunk, offset)
                    for segment in segments:
                        transcript_id = database.add_transcript(
                            session_id, segment.start, segment.end, segment.text
                        )
                        await websocket.send_json(
                            {
                                "type": "transcript",
                                "id": str(transcript_id),
                                "start": segment.start,
                                "end": segment.end,
                                "text": segment.text,
                                "isFinal": True,
                            }
                        )
                        card = accumulator.accept(segment)
                        if card:
                            payload = card.to_dict()
                            database.add_knowledge_card(session_id, payload)
                            await websocket.send_json({"type": "knowledge_card", **payload})
                except Exception as exc:
                    logger.exception("ASR processing failed")
                    await websocket.send_json({"type": "error", "message": f"本地转写失败：{exc}"})
                    await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info("Session %s disconnected", session_id)
    except Exception as exc:
        logger.exception("Audio websocket failed")
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        if session_id and accumulator:
            card = accumulator.flush()
            if card:
                database.add_knowledge_card(session_id, card.to_dict())
