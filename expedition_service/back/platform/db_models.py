from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from expedition_service.back.enums import ExpeditionStatus, MemberState, UserRole


def enum_values(enum_class):
    return [item.value for item in enum_class]


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserRecord(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=enum_values, name="user_role"),
        nullable=False,
    )

    chief_expeditions: Mapped[list["ExpeditionRecord"]] = relationship(back_populates="chief")
    memberships: Mapped[list["ExpeditionMemberRecord"]] = relationship(back_populates="user")


class ExpeditionRecord(TimestampMixin, Base):
    __tablename__ = "expeditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ExpeditionStatus] = mapped_column(
        Enum(ExpeditionStatus, values_callable=enum_values, name="expedition_status"),
        default=ExpeditionStatus.DRAFT,
        nullable=False,
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capacity: Mapped[int] = mapped_column(nullable=False)
    chief_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    chief: Mapped[UserRecord] = relationship(back_populates="chief_expeditions")
    members: Mapped[list["ExpeditionMemberRecord"]] = relationship(
        back_populates="expedition",
        cascade="all, delete-orphan",
    )


class ExpeditionMemberRecord(Base):
    __tablename__ = "expedition_members"
    __table_args__ = (
        UniqueConstraint("expedition_id", "user_id", name="uq_expedition_member_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expedition_id: Mapped[int] = mapped_column(ForeignKey("expeditions.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    state: Mapped[MemberState] = mapped_column(
        Enum(MemberState, values_callable=enum_values, name="member_state"),
        default=MemberState.INVITED,
        nullable=False,
    )
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    expedition: Mapped[ExpeditionRecord] = relationship(back_populates="members")
    user: Mapped[UserRecord] = relationship(back_populates="memberships")
