"""Analytics recording and reporting (database-backed, privacy-preserving)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import Conversation, InteractionEvent, QuestionTopic, ResolutionFeedback
from app.db.session import Database, utcnow
from app.services.topics import classify, keywords

log = logging.getLogger(__name__)

NON_QUESTION_STATUSES = {"greeting"}
UNANSWERED_STATUSES = {"insufficient_evidence"}
FEEDBACK_WINDOW = timedelta(hours=24)


def _by_day(rows) -> dict[str, int]:
    """date() returns str on SQLite and datetime.date on PostgreSQL; normalise to ISO strings."""
    return {str(k)[:10]: int(v) for k, v in rows}


def conversation_hash(conversation_id: str) -> str:
    return hashlib.sha256(f"dy-conv:{conversation_id}".encode()).hexdigest()


def anon_id(conv_hash: str) -> str:
    return f"C-{conv_hash[:8].upper()}"


@dataclass
class FeedbackOutcome:
    recorded: bool
    reason: str  # recorded | duplicate | unknown_message | expired


class AnalyticsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------ recording
    def record_interaction(
        self,
        *,
        conversation_id: str,
        message_id: str,
        asked_at: datetime,
        classification_text: str,
        answer_status: str,
        source_count: int,
        pii_detected: bool,
        latency_ms: int | None,
    ) -> None:
        """Record one exchange. `classification_text` must already be PII-redacted; it is NOT stored."""
        topic = "greeting" if answer_status == "greeting" else classify(classification_text)
        kw = None if answer_status in ("greeting", "refused") else keywords(classification_text)
        chash = conversation_hash(conversation_id)
        with self.db.session() as s:
            conv = s.scalar(select(Conversation).where(Conversation.conversation_hash == chash))
            if conv is None:
                conv = Conversation(conversation_hash=chash, started_at=asked_at, last_activity_at=asked_at,
                                    question_count=0, resolution_status="unconfirmed")
                s.add(conv)
                s.flush()
            conv.last_activity_at = max(conv.last_activity_at, asked_at)
            if answer_status not in NON_QUESTION_STATUSES:
                conv.question_count += 1
                if conv.primary_topic is None or conv.primary_topic in ("greeting", "other"):
                    conv.primary_topic = topic
            elif conv.primary_topic is None:
                conv.primary_topic = "greeting"
            s.add(InteractionEvent(message_id=message_id, conversation_id=conv.id, asked_at=asked_at, topic=topic,
                                   keywords=kw, answer_status=answer_status, source_count=source_count,
                                   pii_detected=pii_detected, latency_ms=latency_ms))

    def record_feedback(self, *, conversation_id: str, message_id: str, resolved: bool) -> FeedbackOutcome:
        """Explicit Yes/No. One feedback per assistant message; latest feedback sets the conversation status.
        Resolution time = first question -> the explicit "Yes"."""
        now = utcnow()
        chash = conversation_hash(conversation_id)
        try:
            with self.db.session() as s:
                event = s.scalar(
                    select(InteractionEvent)
                    .join(Conversation, Conversation.id == InteractionEvent.conversation_id)
                    .where(InteractionEvent.message_id == message_id, Conversation.conversation_hash == chash)
                )
                if event is None or event.answer_status in ("greeting", "refused"):
                    return FeedbackOutcome(False, "unknown_message")
                if now - event.asked_at > FEEDBACK_WINDOW:
                    return FeedbackOutcome(False, "expired")
                if s.scalar(select(ResolutionFeedback.id).where(ResolutionFeedback.message_id == message_id)):
                    return FeedbackOutcome(False, "duplicate")
                conv = s.get(Conversation, event.conversation_id)
                s.add(ResolutionFeedback(conversation_id=conv.id, message_id=message_id, resolved=resolved, created_at=now))
                conv.feedback_at = now
                if resolved:
                    conv.resolution_status = "resolved"
                    conv.resolved_at = now
                    conv.resolution_seconds = max(0.0, (now - conv.started_at).total_seconds())
                else:
                    conv.resolution_status = "unresolved"
                    conv.resolved_at = None
                    conv.resolution_seconds = None
            return FeedbackOutcome(True, "recorded")
        except IntegrityError:  # concurrent duplicate submission
            return FeedbackOutcome(False, "duplicate")

    # ------------------------------------------------------------- reporting
    def report(self, days: int, now: datetime | None = None) -> dict:
        now = now or utcnow()
        start_day = (now - timedelta(days=days - 1)).date()
        start = datetime.combine(start_day, datetime.min.time())
        with self.db.session() as s:
            labels = {t.slug: t.label for t in s.scalars(select(QuestionTopic))}
            in_range = Conversation.started_at >= start
            ev_range = InteractionEvent.asked_at >= start
            is_question = InteractionEvent.answer_status.notin_(NON_QUESTION_STATUSES)

            conversations = s.scalar(select(func.count()).select_from(Conversation).where(in_range,
                                     Conversation.question_count > 0)) or 0
            questions = s.scalar(select(func.count()).select_from(InteractionEvent).where(ev_range, is_question)) or 0

            status_rows = s.execute(
                select(Conversation.resolution_status, func.count())
                .where(in_range, Conversation.question_count > 0)
                .group_by(Conversation.resolution_status)
            ).all()
            status = {"resolved": 0, "unresolved": 0, "unconfirmed": 0} | {k: v for k, v in status_rows}
            confirmed = status["resolved"] + status["unresolved"]
            avg_secs = s.scalar(
                select(func.avg(Conversation.resolution_seconds)).where(
                    in_range, Conversation.resolution_status == "resolved", Conversation.resolution_seconds.isnot(None)
                )
            )

            top = s.execute(
                select(InteractionEvent.topic, func.count().label("n"))
                .where(ev_range, is_question)
                .group_by(InteractionEvent.topic)
                .order_by(func.count().desc(), InteractionEvent.topic)
                .limit(8)
            ).all()

            unanswered_rows = s.execute(
                select(InteractionEvent.topic, InteractionEvent.keywords)
                .where(ev_range, InteractionEvent.answer_status.in_(UNANSWERED_STATUSES))
            ).all()
            out_of_scope = s.scalar(select(func.count()).select_from(InteractionEvent).where(
                ev_range, InteractionEvent.answer_status == "out_of_scope")) or 0

            day = func.date(Conversation.started_at)
            conv_daily = _by_day(s.execute(select(day, func.count()).where(in_range, Conversation.question_count > 0)
                                        .group_by(day)).all())
            eday = func.date(InteractionEvent.asked_at)
            q_daily = _by_day(s.execute(select(eday, func.count()).where(ev_range, is_question).group_by(eday)).all())

            recent = s.execute(
                select(Conversation).where(in_range, Conversation.question_count > 0)
                .order_by(Conversation.started_at.desc()).limit(25)
            ).scalars().all()

        unanswered: dict[str, dict] = {}
        for topic, kw in unanswered_rows:
            u = unanswered.setdefault(topic, {"topic": topic, "label": labels.get(topic, topic), "count": 0, "keywords": {}})
            u["count"] += 1
            for k in (kw or "").split(", "):
                if k:
                    u["keywords"][k] = u["keywords"].get(k, 0) + 1
        unanswered_list = sorted(unanswered.values(), key=lambda u: (-u["count"], u["label"]))
        for u in unanswered_list:
            u["keywords"] = [k for k, _ in sorted(u["keywords"].items(), key=lambda kv: -kv[1])][:4]

        daily = []
        for i in range(days):
            d = (start_day + timedelta(days=i)).isoformat()
            daily.append({"date": d, "conversations": int(conv_daily.get(d, 0)), "questions": int(q_daily.get(d, 0))})

        return {
            "range": {"days": days, "start": start.isoformat() + "Z", "end": now.isoformat() + "Z"},
            "totals": {"conversations": conversations, "questions": questions},
            "resolution": {
                **status,
                "confirmed": confirmed,
                "rate_percent": round(status["resolved"] / confirmed * 100, 1) if confirmed else None,
                "avg_resolution_seconds": round(float(avg_secs), 1) if avg_secs is not None else None,
            },
            "top_topics": [{"topic": t, "label": labels.get(t, t), "count": n} for t, n in top],
            "unanswered": unanswered_list,
            "out_of_scope_count": out_of_scope,
            "daily": daily,
            "recent": [
                {
                    "conversation": anon_id(c.conversation_hash),
                    "topic": c.primary_topic,
                    "topic_label": labels.get(c.primary_topic or "other", "Other / unknown"),
                    "questions": c.question_count,
                    "status": c.resolution_status,
                    "started_at": c.started_at.isoformat() + "Z",
                    "resolution_seconds": round(c.resolution_seconds, 1) if c.resolution_seconds is not None else None,
                }
                for c in recent
            ],
        }


