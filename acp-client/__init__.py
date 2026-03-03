"""
Python ACP Client — bridges ClawWork (Python) to the agent-protocol server (TypeScript).

Mirrors the TypeScript ACPClient over the same WebSocket JSON protocol so both
sides are interchangeable.
"""

from .client import ACPClient, ACPClientConfig
from .types import (
    CommandMessage,
    ResponseMessage,
    EventMessage,
    BashExecutionResult,
    ProcessInfo,
)

__all__ = [
    "ACPClient",
    "ACPClientConfig",
    "CommandMessage",
    "ResponseMessage",
    "EventMessage",
    "BashExecutionResult",
    "ProcessInfo",
]
