import asyncio
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import WebSocket

POLICY_CLOSE_CODE = 1008


@dataclass(frozen=True)
class ExpeditionConnection:
    user_id: int
    websocket: WebSocket
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= datetime.now(timezone.utc)


class ExpeditionEventManager:
    def __init__(self, cleanup_interval_seconds: int):
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._connections: dict[int, dict[WebSocket, ExpeditionConnection]] = defaultdict(dict)
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    async def _ainit_(self):
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_connections())

    async def _adel_(self):
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None
        connections = await self._pop_all_connections()
        await self._close_connections(connections)

    async def connect(self, user_id: int, websocket: WebSocket, expires_at: datetime) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[user_id][websocket] = ExpeditionConnection(
                user_id=user_id,
                websocket=websocket,
                expires_at=expires_at,
            )

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            self._remove_connection(user_id, websocket)

    async def publish(self, user_ids: set[int], event: dict) -> None:
        connections = await self._snapshot_connections(user_ids)
        results = await asyncio.gather(
            *(connection.websocket.send_json(event) for connection in connections),
            return_exceptions=True,
        )
        disconnected = [
            connection
            for connection, result in zip(connections, results)
            if isinstance(result, Exception)
        ]
        await self._disconnect_many(disconnected)

    async def _cleanup_expired_connections(self) -> None:
        while True:
            await asyncio.sleep(self._cleanup_interval_seconds)
            expired_connections = await self._pop_expired_connections()
            await self._close_connections(expired_connections)

    async def _snapshot_connections(self, user_ids: set[int]) -> list[ExpeditionConnection]:
        async with self._lock:
            return [
                connection
                for user_id in user_ids
                for connection in self._connections.get(user_id, {}).values()
            ]

    async def _pop_expired_connections(self) -> list[ExpeditionConnection]:
        async with self._lock:
            expired_connections: list[ExpeditionConnection] = []
            for user_connections in list(self._connections.values()):
                for connection in list(user_connections.values()):
                    if connection.is_expired:
                        expired_connections.append(connection)
                        self._remove_connection(connection.user_id, connection.websocket)
            return expired_connections

    async def _pop_all_connections(self) -> list[ExpeditionConnection]:
        async with self._lock:
            connections = [
                connection
                for user_connections in self._connections.values()
                for connection in user_connections.values()
            ]
            self._connections.clear()
            return connections

    async def _disconnect_many(self, connections: list[ExpeditionConnection]) -> None:
        async with self._lock:
            for connection in connections:
                self._remove_connection(connection.user_id, connection.websocket)

    def _remove_connection(self, user_id: int, websocket: WebSocket) -> None:
        if connections := self._connections.get(user_id):
            connections.pop(websocket, None)
            if not connections:
                self._connections.pop(user_id, None)

    async def _close_connections(self, connections: list[ExpeditionConnection]) -> None:
        await asyncio.gather(
            *(connection.websocket.close(code=POLICY_CLOSE_CODE) for connection in connections),
            return_exceptions=True,
        )
