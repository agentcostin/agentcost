"""
Python ACP Client.

Connects to the TypeScript ACPServer over WebSocket and provides the same
send_command() / execute_bash() / list_processes() interface as the TS client.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from .types import (
    CommandMessage,
    ResponseMessage,
    EventMessage,
    BashExecutionResult,
    ProcessInfo,
)

logger = logging.getLogger("acp_client")


# ── Configuration ────────────────────────────────────────────────────────────

@dataclass
class ACPClientConfig:
    gateway_url: str = "ws://127.0.0.1:8080"
    auth_token: Optional[str] = None
    reconnect: bool = True
    reconnect_interval: float = 5.0        # seconds
    command_timeout: float = 30.0          # seconds
    max_reconnect_attempts: int = 10


# ── Client ───────────────────────────────────────────────────────────────────

class ACPClient:
    """
    Async Python client for the Agent Client Protocol.

    Usage::

        client = ACPClient(ACPClientConfig(gateway_url="ws://127.0.0.1:8080"))
        await client.connect()
        result = await client.send_command("bash.execute", {"command": "ls -la"})
        print(result)
        await client.disconnect()
    """

    def __init__(self, config: ACPClientConfig | None = None):
        self.config = config or ACPClientConfig()
        self._ws: Optional[ClientConnection] = None
        self._connected = False
        self._pending: dict[str, asyncio.Future] = {}
        self._listeners: dict[str, list[Callable]] = {}
        self._reconnect_task: Optional[asyncio.Task] = None
        self._recv_task: Optional[asyncio.Task] = None

    # ── Connection lifecycle ─────────────────────────────────────────────

    async def connect(self) -> None:
        """Open the WebSocket connection to the ACP gateway."""
        extra_headers = {}
        if self.config.auth_token:
            extra_headers["Authorization"] = f"Bearer {self.config.auth_token}"

        try:
            self._ws = await websockets.connect(
                self.config.gateway_url,
                additional_headers=extra_headers,
                open_timeout=10,
            )
            self._connected = True
            logger.info("Connected to ACP gateway at %s", self.config.gateway_url)
            self._emit("connected")
            self._recv_task = asyncio.create_task(self._receive_loop())
        except Exception as exc:
            logger.error("Connection failed: %s", exc)
            raise

    async def disconnect(self) -> None:
        """Close the connection and cancel background tasks."""
        self._connected = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        # Reject all pending requests
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Disconnected"))
        self._pending.clear()
        self._emit("disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Send commands ────────────────────────────────────────────────────

    async def send_command(
        self, command: str, args: dict[str, Any] | None = None
    ) -> Any:
        """
        Send a command to the ACP server and wait for a response.

        Returns the ``data`` field from the server's ResponseMessage on success.
        Raises ``RuntimeError`` on command failure or timeout.
        """
        if not self._connected or self._ws is None:
            raise ConnectionError("Not connected to ACP gateway")

        msg = CommandMessage(command=command, args=args or {})
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg.id] = future

        try:
            await self._ws.send(json.dumps(msg.to_dict()))
        except Exception as exc:
            self._pending.pop(msg.id, None)
            raise ConnectionError(f"Send failed: {exc}") from exc

        try:
            return await asyncio.wait_for(future, timeout=self.config.command_timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg.id, None)
            raise TimeoutError(f"Command timed out: {command}")

    # ── Convenience wrappers ─────────────────────────────────────────────

    async def execute_bash(
        self, command: str, *, cwd: str | None = None
    ) -> BashExecutionResult:
        """Execute a bash command and return a typed result."""
        args: dict[str, Any] = {"command": command}
        if cwd:
            args["cwd"] = cwd
        data = await self.send_command("bash.execute", args)
        return BashExecutionResult.from_dict(data)

    async def list_processes(self) -> list[ProcessInfo]:
        data = await self.send_command("process.list")
        return [ProcessInfo.from_dict(p) for p in (data or [])]

    async def spawn_process(
        self,
        command: str,
        args: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> ProcessInfo:
        data = await self.send_command(
            "process.spawn",
            {"command": command, "args": args or [], "options": options or {}},
        )
        return ProcessInfo.from_dict(data)

    async def kill_process(
        self, process_id: str, signal: str = "SIGTERM"
    ) -> bool:
        data = await self.send_command(
            "process.kill", {"processId": process_id, "signal": signal}
        )
        return bool(data and data.get("success"))

    async def create_file(
        self, filename: str, content: str, *, cwd: str | None = None
    ) -> dict:
        """Create a file on the remote host via the ACP server."""
        return await self.send_command(
            "file.create",
            {"filename": filename, "content": content, "cwd": cwd},
        )

    async def get_status(self) -> dict:
        """Request agent status from the server."""
        return await self.send_command("agent.info")

    # ── Event system ─────────────────────────────────────────────────────

    def on(self, event: str, callback: Callable) -> None:
        self._listeners.setdefault(event, []).append(callback)

    def off(self, event: str, callback: Callable) -> None:
        if event in self._listeners:
            self._listeners[event] = [
                cb for cb in self._listeners[event] if cb is not callback
            ]

    def _emit(self, event: str, *args: Any) -> None:
        for cb in self._listeners.get(event, []):
            try:
                cb(*args)
            except Exception:
                logger.exception("Error in event listener for %s", event)

    # ── Internal receive loop ────────────────────────────────────────────

    async def _receive_loop(self) -> None:
        """Background task that reads messages from the WebSocket."""
        try:
            assert self._ws is not None
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from gateway")
                    continue

                msg_type = msg.get("type")

                if msg_type == "response":
                    resp = ResponseMessage.from_dict(msg)
                    future = self._pending.pop(resp.request_id, None)
                    if future and not future.done():
                        if resp.success:
                            future.set_result(resp.data)
                        else:
                            future.set_exception(
                                RuntimeError(resp.error or "Command failed")
                            )

                elif msg_type == "event":
                    ev = EventMessage.from_dict(msg)
                    self._emit("event", ev)
                    self._emit(f"event:{ev.event}", ev.data)

                elif msg_type == "error":
                    logger.error("Server error: %s", msg.get("error"))
                    self._emit("error", msg.get("error"))

                else:
                    self._emit("message", msg)

        except websockets.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except asyncio.CancelledError:
            return
        finally:
            self._connected = False
            self._emit("disconnected")
            if self.config.reconnect:
                self._reconnect_task = asyncio.create_task(self._try_reconnect())

    async def _try_reconnect(self) -> None:
        attempts = 0
        while attempts < self.config.max_reconnect_attempts:
            attempts += 1
            logger.info("Reconnect attempt %d/%d in %.1fs …",
                        attempts, self.config.max_reconnect_attempts,
                        self.config.reconnect_interval)
            await asyncio.sleep(self.config.reconnect_interval)
            try:
                await self.connect()
                return
            except Exception as exc:
                logger.warning("Reconnect failed: %s", exc)
        logger.error("Max reconnect attempts reached — giving up")
