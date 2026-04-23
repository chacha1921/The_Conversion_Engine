"""
Per-(company_id, contact_id) conversation state store.
Isolates threads so context never leaks between contacts at the same company.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class Message:
    role: str            # "agent" | "prospect"
    content: str
    channel: str         # "email" | "sms" | "voice"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Thread:
    company_id: str
    contact_id: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    segment: Optional[str] = None
    messages: list[Message] = field(default_factory=list)
    outreach_count: int = 0
    opted_out: bool = False           # STOP command received
    last_activity: Optional[str] = None

    def add(self, role: str, content: str, channel: str) -> None:
        self.messages.append(Message(role=role, content=content, channel=channel))
        self.last_activity = datetime.now(timezone.utc).isoformat()
        if role == "agent":
            self.outreach_count += 1

    @property
    def key(self) -> str:
        return f"{self.company_id}::{self.contact_id}"

    def to_dict(self) -> dict:
        return {
            "company_id": self.company_id,
            "contact_id": self.contact_id,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "segment": self.segment,
            "messages": [vars(m) for m in self.messages],
            "outreach_count": self.outreach_count,
            "opted_out": self.opted_out,
            "last_activity": self.last_activity,
        }


class ThreadStore:
    """
    In-memory store with optional JSON persistence.
    Key: "{company_id}::{contact_id}" — guarantees isolation.
    """

    def __init__(self, persist_path: Optional[str] = None):
        self._threads: dict[str, Thread] = {}
        self._persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load(persist_path)

    def get_or_create(
        self,
        company_id: str,
        contact_id: str,
        **kwargs,
    ) -> Thread:
        key = f"{company_id}::{contact_id}"
        if key not in self._threads:
            self._threads[key] = Thread(
                company_id=company_id,
                contact_id=contact_id,
                **kwargs,
            )
        return self._threads[key]

    def get(self, company_id: str, contact_id: str) -> Optional[Thread]:
        return self._threads.get(f"{company_id}::{contact_id}")

    def mark_opted_out(self, company_id: str, contact_id: str) -> None:
        thread = self.get(company_id, contact_id)
        if thread:
            thread.opted_out = True
        self._save()

    def save(self) -> None:
        self._save()

    def _save(self) -> None:
        if not self._persist_path:
            return
        Path(self._persist_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._persist_path, "w") as f:
            json.dump(
                {k: v.to_dict() for k, v in self._threads.items()},
                f, indent=2,
            )

    def _load(self, path: str) -> None:
        with open(path) as f:
            data = json.load(f)
        for key, d in data.items():
            messages = [Message(**m) for m in d.pop("messages", [])]
            thread = Thread(**d)
            thread.messages = messages
            self._threads[key] = thread


# Module-level singleton — import this in all handlers
_store_path = os.getenv("THREAD_STORE_PATH", "data/threads.json")
store = ThreadStore(persist_path=_store_path)
