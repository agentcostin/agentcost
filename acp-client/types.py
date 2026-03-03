"""
Message types for the Agent Client Protocol.
Mirrors the TypeScript definitions in agent-protocol/src/types/index.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import time
import uuid


def generate_id() -> str:
    return str(uuid.uuid4())


def now_ms() -> int:
    return int(time.time() * 1000)


# ── Message types ────────────────────────────────────────────────────────────

class MessageType(str, Enum):
    COMMAND = "command"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


@dataclass
class CommandMessage:
    command: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=generate_id)
    type: str = field(default="command", init=False)
    timestamp: int = field(default_factory=now_ms)
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"id": self.id, "type": self.type, "command": self.command,
             "args": self.args, "timestamp": self.timestamp}
        if self.session_id:
            d["sessionId"] = self.session_id
        return d


@dataclass
class ResponseMessage:
    request_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    id: str = field(default_factory=generate_id)
    type: str = field(default="response", init=False)
    timestamp: int = field(default_factory=now_ms)

    @classmethod
    def from_dict(cls, d: dict) -> "ResponseMessage":
        return cls(
            id=d.get("id", generate_id()),
            request_id=d.get("requestId", ""),
            success=d.get("success", False),
            data=d.get("data"),
            error=d.get("error"),
            timestamp=d.get("timestamp", now_ms()),
        )


@dataclass
class EventMessage:
    event: str
    data: Any = None
    id: str = field(default_factory=generate_id)
    type: str = field(default="event", init=False)
    timestamp: int = field(default_factory=now_ms)

    @classmethod
    def from_dict(cls, d: dict) -> "EventMessage":
        return cls(
            id=d.get("id", generate_id()),
            event=d.get("event", ""),
            data=d.get("data"),
            timestamp=d.get("timestamp", now_ms()),
        )


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class BashExecutionResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    approved: bool = True
    duration: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "BashExecutionResult":
        return cls(
            stdout=d.get("stdout", ""),
            stderr=d.get("stderr", ""),
            exit_code=d.get("exitCode", 0),
            approved=d.get("approved", True),
            duration=d.get("duration", 0.0),
        )


@dataclass
class ProcessInfo:
    id: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    pid: Optional[int] = None
    start_time: int = 0
    status: str = "running"
    exit_code: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> "ProcessInfo":
        return cls(
            id=d.get("id", ""),
            command=d.get("command", ""),
            args=d.get("args", []),
            pid=d.get("pid"),
            start_time=d.get("startTime", 0),
            status=d.get("status", "running"),
            exit_code=d.get("exitCode"),
        )
