"""In-process event bus for live pipeline visualization.

Every stage of an investigation (evidence build, gate check, Gemma reasoning,
grounding, confidence scoring, export) publishes a small JSON-able event here.
The SSE endpoint in main.py subscribes and streams them to the frontend, so
the "what is the backend doing right now" pipeline animation is driven by
real stage transitions, not a fake timer.

Deliberately dependency-free (no Redis/broker) — a hackathon-scale, single
-process service doesn't need one, and it keeps the reasoning pipeline
importable/testable without a running event loop.
"""
from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional

# Canonical stage ids, in pipeline order — the frontend keys its stepper off these.
STAGES = [
    "evidence_build",
    "evidence_gate",
    "gemma_reasoning",
    "model_gate",
    "grounding",
    "confidence",
    "complete",
    "export",
]


@dataclass
class PipelineEvent:
    case_id: str
    stage: str            # one of STAGES, or "error"
    status: str           # "start" | "ok" | "fail" | "skip"
    detail: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_json(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "stage": self.stage,
            "status": self.status,
            "detail": self.detail,
            "meta": self.meta,
            "ts": self.ts,
        }


class EventBus:
    """Fan-out pub/sub: each subscriber gets its own queue so a slow client
    (or one that navigated away) can never block another's stream."""

    def __init__(self, history_size: int = 200):
        self._subscribers: List["queue.Queue[PipelineEvent]"] = []
        self._lock = Lock()
        self._history: List[PipelineEvent] = []
        self._history_size = history_size

    def publish(self, event: PipelineEvent) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_size:
                self._history.pop(0)
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # slow subscriber drops a frame rather than backpressure the pipeline

    def emit(self, case_id: str, stage: str, status: str, detail: str = "", **meta: Any) -> None:
        self.publish(PipelineEvent(case_id=case_id, stage=stage, status=status, detail=detail, meta=meta))

    def subscribe(self) -> "queue.Queue[PipelineEvent]":
        q: "queue.Queue[PipelineEvent]" = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[PipelineEvent]") -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def recent(self, case_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._history)
        if case_id:
            items = [e for e in items if e.case_id == case_id]
        return [e.to_json() for e in items[-limit:]]


bus = EventBus()
