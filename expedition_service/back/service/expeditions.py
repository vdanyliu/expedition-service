from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from expedition_service.back.enums import ExpeditionEventType, ExpeditionStatus, MemberState, UserRole
from expedition_service.back.models import ExpeditionCreateModel, ExpeditionMemberModel, ExpeditionModel, UserModel
from expedition_service.back.platform.database import Database
from expedition_service.back.platform.db_models import ExpeditionMemberRecord, ExpeditionRecord, UserRecord
from expedition_service.back.platform.errors import DomainError
from expedition_service.back.platform.events import ExpeditionEventManager


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ExpeditionService:
    def __init__(self, db: Database, events: ExpeditionEventManager):
        self.db = db
        self.events = events

    async def create_expedition(
        self,
        expedition_model: ExpeditionCreateModel,
        current_user: UserModel,
    ) -> ExpeditionModel:
        if current_user.role != UserRole.CHIEF:
            raise DomainError(403, "Only chiefs can create expeditions")

        async with self.db.session() as session:
            expedition_record = ExpeditionRecord(
                title=expedition_model.title,
                description=expedition_model.description,
                start_at=_utc_now(),
                end_at=None,
                capacity=expedition_model.capacity,
                chief_id=expedition_model.chief_id,
            )
            session.add(expedition_record)
            await session.commit()
            await session.refresh(expedition_record)
            return self._to_expedition_model(expedition_record)

    async def list_expeditions(self, current_user: UserModel) -> list[ExpeditionModel]:
        async with self.db.session() as session:
            member_expedition_ids = select(ExpeditionMemberRecord.expedition_id).where(
                ExpeditionMemberRecord.user_id == current_user.id
            )
            result = await session.scalars(
                select(ExpeditionRecord)
                .where(or_(ExpeditionRecord.chief_id == current_user.id, ExpeditionRecord.id.in_(member_expedition_ids)))
                .order_by(ExpeditionRecord.id)
            )
            return [self._to_expedition_model(expedition) for expedition in result.all()]

    async def get_expedition(self, expedition_id: int, current_user: UserModel) -> ExpeditionModel:
        async with self.db.session() as session:
            expedition_record = await self._get_expedition(session, expedition_id)
            await self._require_access(session, expedition_record, current_user)
            return self._to_expedition_model(expedition_record)

    async def list_members(self, expedition_id: int, current_user: UserModel) -> list[ExpeditionMemberModel]:
        async with self.db.session() as session:
            expedition_record = await self._get_expedition(session, expedition_id)
            await self._require_access(session, expedition_record, current_user)
            result = await session.scalars(
                select(ExpeditionMemberRecord)
                .where(ExpeditionMemberRecord.expedition_id == expedition_id)
                .order_by(ExpeditionMemberRecord.id)
            )
            return [self._to_member_model(member) for member in result.all()]

    async def invite_member(
        self,
        expedition_id: int,
        invited_user_id: int,
        current_user: UserModel,
    ) -> ExpeditionMemberModel:
        async with self.db.session() as session:
            expedition_record = await self._get_expedition(session, expedition_id)
            self._require_chief(expedition_record, current_user)
            if expedition_record.status != ExpeditionStatus.DRAFT:
                raise DomainError(400, "Members can be invited only while expedition is draft")

            invited_user_record = await session.get(UserRecord, invited_user_id)
            if invited_user_record is None:
                raise DomainError(404, "User not found")
            if invited_user_record.role != UserRole.MEMBER:
                raise DomainError(400, "Only users with member role can be invited")

            existing_member = await session.scalar(
                select(ExpeditionMemberRecord).where(
                    ExpeditionMemberRecord.expedition_id == expedition_id,
                    ExpeditionMemberRecord.user_id == invited_user_id,
                )
            )
            if existing_member is not None:
                raise DomainError(409, "User is already invited to this expedition")

            member_record = ExpeditionMemberRecord(
                expedition_id=expedition_id,
                user_id=invited_user_id,
                state=MemberState.INVITED,
            )
            session.add(member_record)
            await session.commit()
            await session.refresh(member_record)
            await self._publish_member_event(session, ExpeditionEventType.MEMBER_INVITED, expedition_id, member_record)
            return self._to_member_model(member_record)

    async def confirm_membership(self, expedition_id: int, current_user: UserModel) -> ExpeditionMemberModel:
        async with self.db.session() as session:
            expedition_record = await self._get_expedition(session, expedition_id)
            if expedition_record.status != ExpeditionStatus.DRAFT:
                raise DomainError(400, "Members can confirm only while expedition is draft")

            member_record = await session.scalar(
                select(ExpeditionMemberRecord).where(
                    ExpeditionMemberRecord.expedition_id == expedition_id,
                    ExpeditionMemberRecord.user_id == current_user.id,
                )
            )
            if member_record is None:
                raise DomainError(404, "Invitation not found")
            if member_record.state != MemberState.INVITED:
                raise DomainError(400, "Only invited members can confirm participation")

            member_record.state = MemberState.CONFIRMED
            member_record.confirmed_at = _utc_now()
            await session.commit()
            await session.refresh(member_record)
            await self._publish_member_event(session, ExpeditionEventType.MEMBER_CONFIRMED, expedition_id, member_record)
            return self._to_member_model(member_record)

    async def update_status(
        self,
        expedition_id: int,
        requested_status: ExpeditionStatus,
        current_user: UserModel,
    ) -> ExpeditionModel:
        async with self.db.session() as session:
            expedition_record = await self._get_expedition(session, expedition_id)
            self._require_chief(expedition_record, current_user)

            old_status = expedition_record.status
            match requested_status:
                case ExpeditionStatus.READY:
                    self._require_current_status(
                        expedition_record,
                        ExpeditionStatus.DRAFT,
                        "Only draft expeditions can be marked ready",
                    )
                case ExpeditionStatus.ACTIVE:
                    self._require_current_status(
                        expedition_record,
                        ExpeditionStatus.READY,
                        "Only ready expeditions can be started",
                    )
                    await self._validate_activation(session, expedition_record)
                case ExpeditionStatus.FINISHED:
                    self._require_current_status(
                        expedition_record,
                        ExpeditionStatus.ACTIVE,
                        "Only active expeditions can be finished",
                    )
                    expedition_record.end_at = _utc_now()
                case _:
                    raise DomainError(400, "Unsupported expedition status transition")

            expedition_record.status = requested_status
            await session.commit()
            await session.refresh(expedition_record)
            await self._publish_status_event(session, expedition_record.id, old_status, requested_status)
            return self._to_expedition_model(expedition_record)

    async def _validate_activation(self, session: AsyncSession, expedition_record: ExpeditionRecord) -> None:
        if _as_utc(expedition_record.start_at) > _utc_now():
            raise DomainError(400, "Expedition cannot start before start_at")

        confirmed_user_ids = await self._get_confirmed_user_ids(session, expedition_record.id)
        confirmed_count = len(confirmed_user_ids)
        if confirmed_count < 2:
            raise DomainError(400, "Expedition requires at least two confirmed members")
        if confirmed_count > expedition_record.capacity:
            raise DomainError(400, "Confirmed members count exceeds expedition capacity")

        other_active_member = await session.scalar(
            select(ExpeditionMemberRecord.user_id)
            .join(ExpeditionRecord, ExpeditionRecord.id == ExpeditionMemberRecord.expedition_id)
            .where(
                ExpeditionMemberRecord.user_id.in_(confirmed_user_ids),
                ExpeditionMemberRecord.state == MemberState.CONFIRMED,
                ExpeditionRecord.status == ExpeditionStatus.ACTIVE,
                ExpeditionRecord.id != expedition_record.id,
            )
            .limit(1)
        )
        if other_active_member is not None:
            raise DomainError(400, "Confirmed member already participates in another active expedition")

    async def _get_expedition(self, session: AsyncSession, expedition_id: int) -> ExpeditionRecord:
        expedition_record = await session.get(ExpeditionRecord, expedition_id)
        if expedition_record is None:
            raise DomainError(404, "Expedition not found")
        return expedition_record

    def _require_chief(self, expedition_record: ExpeditionRecord, current_user: UserModel) -> None:
        if expedition_record.chief_id != current_user.id:
            raise DomainError(403, "Only expedition chief can perform this action")

    async def _require_access(
        self,
        session: AsyncSession,
        expedition_record: ExpeditionRecord,
        current_user: UserModel,
    ) -> None:
        if expedition_record.chief_id == current_user.id:
            return
        member_id = await session.scalar(
            select(ExpeditionMemberRecord.id).where(
                ExpeditionMemberRecord.expedition_id == expedition_record.id,
                ExpeditionMemberRecord.user_id == current_user.id,
            )
        )
        if member_id is None:
            raise DomainError(403, "Expedition is not available for current user")

    def _require_current_status(
        self,
        expedition_record: ExpeditionRecord,
        expected_status: ExpeditionStatus,
        message: str,
    ) -> None:
        if expedition_record.status != expected_status:
            raise DomainError(400, message)

    async def _get_confirmed_user_ids(self, session: AsyncSession, expedition_id: int) -> list[int]:
        result = await session.scalars(
            select(ExpeditionMemberRecord.user_id).where(
                ExpeditionMemberRecord.expedition_id == expedition_id,
                ExpeditionMemberRecord.state == MemberState.CONFIRMED,
            )
        )
        return list(result.all())

    async def _get_event_recipient_user_ids(self, session: AsyncSession, expedition_id: int) -> set[int]:
        chief_id = await session.scalar(select(ExpeditionRecord.chief_id).where(ExpeditionRecord.id == expedition_id))
        member_ids = await session.scalars(
            select(ExpeditionMemberRecord.user_id).where(ExpeditionMemberRecord.expedition_id == expedition_id)
        )
        recipient_user_ids = set(member_ids.all())
        if chief_id is not None:
            recipient_user_ids.add(chief_id)
        return recipient_user_ids

    async def _publish_member_event(
        self,
        session: AsyncSession,
        event_type: ExpeditionEventType,
        expedition_id: int,
        member_record: ExpeditionMemberRecord,
    ) -> None:
        await self.events.publish(
            await self._get_event_recipient_user_ids(session, expedition_id),
            {
                "type": event_type.value,
                "expedition_id": expedition_id,
                "member_id": member_record.id,
                "user_id": member_record.user_id,
                "state": member_record.state.value,
            },
        )

    async def _publish_status_event(
        self,
        session: AsyncSession,
        expedition_id: int,
        old_status: ExpeditionStatus,
        new_status: ExpeditionStatus,
    ) -> None:
        await self.events.publish(
            await self._get_event_recipient_user_ids(session, expedition_id),
            {
                "type": ExpeditionEventType.EXPEDITION_STATUS.value,
                "expedition_id": expedition_id,
                "old_status": old_status.value,
                "new_status": new_status.value,
            },
        )

    @staticmethod
    def _to_expedition_model(expedition_record: ExpeditionRecord) -> ExpeditionModel:
        return ExpeditionModel(
            id=expedition_record.id,
            title=expedition_record.title,
            description=expedition_record.description,
            status=expedition_record.status,
            start_at=expedition_record.start_at,
            end_at=expedition_record.end_at,
            capacity=expedition_record.capacity,
            chief_id=expedition_record.chief_id,
            created_at=expedition_record.created_at,
            updated_at=expedition_record.updated_at,
        )

    @staticmethod
    def _to_member_model(member_record: ExpeditionMemberRecord) -> ExpeditionMemberModel:
        return ExpeditionMemberModel(
            id=member_record.id,
            expedition_id=member_record.expedition_id,
            user_id=member_record.user_id,
            state=member_record.state,
            invited_at=member_record.invited_at,
            confirmed_at=member_record.confirmed_at,
        )
