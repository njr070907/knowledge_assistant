from pathlib import Path

from app.database import Database


def test_session_and_transcript_round_trip(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.start_session("session-1", "线性代数", "https://example.test/video", "测试")
    transcript_id = database.add_transcript("session-1", 1.0, 2.5, "初等变换不改变矩阵的秩")

    rows = database.recent_transcripts("session-1")

    assert transcript_id > 0
    assert rows == [
        {
            "id": transcript_id,
            "start_seconds": 1.0,
            "end_seconds": 2.5,
            "text": "初等变换不改变矩阵的秩",
        }
    ]

