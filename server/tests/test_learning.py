import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.database import Database
from app.learning import TopicAccumulator, detect_subject, render_study_markdown
from app.llm import LocalLlmClient
from app.notion import NotionClient
from app.study_service import StudyService


def segment(start: float, end: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(start=start, end=end, text=text)


def test_subject_detection_prefers_course_specific_profile() -> None:
    profile = detect_subject("一生一芯：流水线处理器", "使用 RISC-V 指令和 Verilog 实现寄存器堆。")
    assert profile.id == "ysyx"


def test_topic_accumulator_emits_traceable_card() -> None:
    accumulator = TopicAccumulator("线性代数：矩阵的秩", topic_seconds=10)
    assert accumulator.accept(segment(0, 4, "初等行变换对应可逆的线性操作。")) is None
    card = accumulator.accept(segment(4, 12, "因此初等变换不会改变矩阵的秩。"))

    assert card is not None
    assert card.subject == "线性代数"
    assert card.start == 0
    assert card.end == 12
    assert "秩" in card.title


def test_finalize_builds_local_markdown_without_network(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, llm_enabled=False, notion_token="", notion_parent_page_id="")
    database = Database(tmp_path / "study.sqlite3")
    database.start_session("s1", "高等数学：导数", "https://example.test/course", "测试")
    database.add_transcript("s1", 65, 70, "导数描述函数在一点附近的瞬时变化率。")
    service = StudyService(database, LocalLlmClient(settings), NotionClient(settings), tmp_path / "notes")

    result = asyncio.run(service.finalize("s1"))

    assert result["subject"] == "高等数学"
    assert result["cardCount"] == 1
    assert result["syncStatus"] == "not_configured"
    assert "## 核心知识点" in result["markdown"]
    assert "`01:05" in result["markdown"]
    assert Path(result["localPath"]).exists()


def test_markdown_contains_review_schedule() -> None:
    markdown = render_study_markdown(
        "测试课程",
        None,
        "通用课程",
        [],
        [{"start_seconds": 2, "text": "测试内容。"}],
    )
    assert "明天" in markdown
    assert "3 天后" in markdown
    assert "7 天后" in markdown


def test_external_llm_endpoint_is_rejected(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, llm_base_url="https://example.com/v1")
    try:
        LocalLlmClient(settings)
    except ValueError as exc:
        assert "必须指向本机" in str(exc)
    else:
        raise AssertionError("external LLM URL should be rejected")


def test_notion_queue_completes_with_provider(tmp_path: Path) -> None:
    class FakeNotion:
        enabled = True

        async def create_page(self, markdown: str) -> SimpleNamespace:
            assert "## 核心知识点" in markdown
            return SimpleNamespace(id="notion-page-1", url="https://notion.test/page")

    settings = Settings(data_dir=tmp_path, llm_enabled=False)
    database = Database(tmp_path / "sync.sqlite3")
    database.start_session("s2", "马原：矛盾", "https://example.test/marx", "测试")
    database.add_transcript("s2", 0, 5, "矛盾双方既对立又统一。")
    service = StudyService(database, LocalLlmClient(settings), FakeNotion(), tmp_path / "notes")

    result = asyncio.run(service.finalize("s2"))

    assert result["syncStatus"] == "completed"
    assert result["notionPageId"] == "notion-page-1"
    assert database.pending_sync_jobs() == []
