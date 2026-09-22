from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from typing import Iterable, Protocol


class TimedText(Protocol):
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SubjectProfile:
    id: str
    name: str
    keywords: tuple[str, ...]
    review_prompt: str


@dataclass(frozen=True)
class KnowledgeCard:
    id: str
    subject: str
    title: str
    summary: str
    key_points: tuple[str, ...]
    question: str
    start: float
    end: float
    source: str = "local-rules"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["keyPoints"] = list(payload.pop("key_points"))
        return payload


SUBJECTS = (
    SubjectProfile(
        "linear-algebra",
        "线性代数",
        ("线性代数", "矩阵", "向量", "线性变换", "行列式", "特征值", "特征向量", "秩", "基", "维数"),
        "这个结论依赖哪些定义或不变量？请说明推理链。",
    ),
    SubjectProfile(
        "calculus",
        "高等数学",
        ("高等数学", "极限", "导数", "微分", "积分", "级数", "连续", "偏导", "梯度", "微分方程"),
        "这一步为什么成立？它使用了哪些条件，条件缺失时会怎样？",
    ),
    SubjectProfile(
        "marxism",
        "马克思主义基本原理",
        ("马原", "马克思", "辩证法", "唯物主义", "生产力", "生产关系", "剩余价值", "实践", "矛盾"),
        "请用自己的话说明概念、依据与现实例子之间的关系。",
    ),
    SubjectProfile(
        "ysyx",
        "一生一芯",
        ("一生一芯", "RISC-V", "Verilog", "处理器", "流水线", "指令", "寄存器", "总线", "缓存", "NPC", "NEMU"),
        "如果要实现或调试这一部分，你会先检查哪条数据通路或不变量？",
    ),
)

GENERIC_SUBJECT = SubjectProfile(
    "general",
    "通用课程",
    (),
    "刚才这个知识点解决了什么问题？请不用原句解释一遍。",
)

SENTENCE_SPLIT = re.compile(r"(?<=[。！？；!?;])\s*")
FILLER_PREFIX = re.compile(r"^(所以|那么|然后|这里|我们可以看到|也就是说|因此)[，,\s]*")


def detect_subject(title: str, text: str = "") -> SubjectProfile:
    haystack = f"{title}\n{text}".lower()
    scored = []
    for profile in SUBJECTS:
        score = sum(3 if keyword.lower() in title.lower() else 1 for keyword in profile.keywords if keyword.lower() in haystack)
        scored.append((score, profile))
    best_score, best_profile = max(scored, key=lambda item: item[0])
    return best_profile if best_score > 0 else GENERIC_SUBJECT


def clean_sentence(text: str) -> str:
    return FILLER_PREFIX.sub("", " ".join(text.split())).strip(" ，,。")


def _sentences(text: str) -> list[str]:
    return [clean_sentence(part) for part in SENTENCE_SPLIT.split(text) if clean_sentence(part)]


def build_card(session_title: str, segments: Iterable[TimedText]) -> KnowledgeCard | None:
    items = list(segments)
    if not items:
        return None
    combined = "".join(item.text.strip() for item in items)
    sentences = _sentences(combined)
    if not sentences:
        return None

    subject = detect_subject(session_title, combined)
    informative = max(
        sentences,
        key=lambda sentence: (
            sum(keyword.lower() in sentence.lower() for keyword in subject.keywords),
            any(marker in sentence for marker in ("因为", "因此", "定义", "不变", "等于", "可以", "意味着")),
            min(len(sentence), 48),
        ),
    )
    title = informative[:34] + ("…" if len(informative) > 34 else "")
    key_points = tuple(sentences[:3])
    summary = "；".join(key_points)[:190]
    return KnowledgeCard(
        id=str(uuid.uuid4()),
        subject=subject.name,
        title=title,
        summary=summary,
        key_points=key_points,
        question=subject.review_prompt,
        start=items[0].start,
        end=items[-1].end,
    )


class TopicAccumulator:
    def __init__(self, session_title: str, topic_seconds: float = 36.0, max_chars: int = 320) -> None:
        self.session_title = session_title
        self.topic_seconds = topic_seconds
        self.max_chars = max_chars
        self._segments: list[TimedText] = []

    def accept(self, segment: TimedText) -> KnowledgeCard | None:
        self._segments.append(segment)
        duration = self._segments[-1].end - self._segments[0].start
        characters = sum(len(item.text) for item in self._segments)
        if duration < self.topic_seconds and characters < self.max_chars:
            return None
        return self.flush()

    def flush(self) -> KnowledgeCard | None:
        card = build_card(self.session_title, self._segments)
        self._segments = []
        return card


def format_timestamp(seconds: float) -> str:
    value = max(0, int(seconds))
    return f"{value // 60:02d}:{value % 60:02d}"


def render_study_markdown(
    title: str,
    url: str | None,
    subject: str,
    cards: list[dict[str, object]],
    transcripts: list[dict[str, object]],
) -> str:
    lines = [f"# {title}", "", f"- 学科：{subject}"]
    if url:
        lines.append(f"- 原视频：{url}")
    lines.extend(["", "## 核心知识点", ""])

    if cards:
        for card in cards:
            start = format_timestamp(float(card["start_seconds"]))
            end = format_timestamp(float(card["end_seconds"]))
            lines.extend(
                [
                    f"### {card['title']}",
                    f"时间：`{start}–{end}`",
                    "",
                    str(card["summary"]),
                    "",
                ]
            )
    else:
        lines.append("本次会话尚未形成完整知识点。")

    lines.extend(["", "## 主动回忆", ""])
    questions = [str(card["question"]) for card in cards if card.get("question")]
    for index, question in enumerate(dict.fromkeys(questions), start=1):
        lines.append(f"{index}. {question}")
    if not questions:
        lines.append("1. 请不用原句解释这节课解决了什么问题。")

    lines.extend(["", "## 复习安排", "", "- [ ] 明天：闭卷回答主动回忆题", "- [ ] 3 天后：重做一个例题或复述论证", "- [ ] 7 天后：把本节与前后章节连接起来", "", "<details>", "<summary>带时间戳的逐字稿</summary>", ""])
    for row in transcripts:
        lines.append(f"- `{format_timestamp(float(row['start_seconds']))}` {row['text']}")
    lines.extend(["", "</details>"])
    return "\n".join(lines)
