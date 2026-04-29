from collections.abc import Callable

from fastapi import APIRouter, Depends, status

from expedition_service.back.api.requests import (
    ExpeditionCreateRequest,
    ExpeditionStatusUpdateRequest,
    InviteMemberRequest,
)
from expedition_service.back.api.responses import ExpeditionMemberResponse, ExpeditionResponse
from expedition_service.back.models import UserModel
from expedition_service.back.service.expeditions import ExpeditionService


def create_router(
    service: ExpeditionService,
    current_user_dependency: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/expeditions", tags=["expeditions"])

    @router.post("", response_model=ExpeditionResponse, status_code=status.HTTP_201_CREATED)
    async def create_expedition(
        payload: ExpeditionCreateRequest,
        current_user: UserModel = Depends(current_user_dependency),
    ) -> ExpeditionResponse:
        return ExpeditionResponse.from_model(await service.create_expedition(payload.to_model(current_user.id), current_user))

    @router.get("", response_model=list[ExpeditionResponse])
    async def list_expeditions(
        current_user: UserModel = Depends(current_user_dependency),
    ) -> list[ExpeditionResponse]:
        return [ExpeditionResponse.from_model(item) for item in await service.list_expeditions(current_user)]

    @router.get("/{expedition_id}", response_model=ExpeditionResponse)
    async def get_expedition(
        expedition_id: int,
        current_user: UserModel = Depends(current_user_dependency),
    ) -> ExpeditionResponse:
        return ExpeditionResponse.from_model(await service.get_expedition(expedition_id, current_user))

    @router.get("/{expedition_id}/members", response_model=list[ExpeditionMemberResponse])
    async def list_members(
        expedition_id: int,
        current_user: UserModel = Depends(current_user_dependency),
    ) -> list[ExpeditionMemberResponse]:
        return [ExpeditionMemberResponse.from_model(item) for item in await service.list_members(expedition_id, current_user)]

    @router.post("/{expedition_id}/members/invite", response_model=ExpeditionMemberResponse)
    async def invite_member(
        expedition_id: int,
        payload: InviteMemberRequest,
        current_user: UserModel = Depends(current_user_dependency),
    ) -> ExpeditionMemberResponse:
        return ExpeditionMemberResponse.from_model(await service.invite_member(expedition_id, payload.user_id, current_user))

    @router.post("/{expedition_id}/members/confirm", response_model=ExpeditionMemberResponse)
    async def confirm_membership(
        expedition_id: int,
        current_user: UserModel = Depends(current_user_dependency),
    ) -> ExpeditionMemberResponse:
        return ExpeditionMemberResponse.from_model(await service.confirm_membership(expedition_id, current_user))

    @router.patch("/{expedition_id}/status", response_model=ExpeditionResponse)
    async def update_status(
        expedition_id: int,
        payload: ExpeditionStatusUpdateRequest,
        current_user: UserModel = Depends(current_user_dependency),
    ) -> ExpeditionResponse:
        return ExpeditionResponse.from_model(await service.update_status(expedition_id, payload.status, current_user))

    return router
