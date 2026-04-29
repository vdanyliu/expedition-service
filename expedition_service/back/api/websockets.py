from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from expedition_service.back.platform.errors import DomainError
from expedition_service.back.platform.events import ExpeditionEventManager
from expedition_service.back.service.auth import AuthService


def create_router(
    auth_service: AuthService,
    events: ExpeditionEventManager,
) -> APIRouter:
    router = APIRouter(tags=["websocket"])

    @router.websocket("/ws/expeditions")
    async def expedition_events(websocket: WebSocket, token: str = Query(...)):
        try:
            auth_context = await auth_service.authenticate_token(token)
        except DomainError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await events.connect(
            user_id=auth_context.user.id,
            websocket=websocket,
            expires_at=auth_context.expires_at,
        )
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await events.disconnect(auth_context.user.id, websocket)

    return router
