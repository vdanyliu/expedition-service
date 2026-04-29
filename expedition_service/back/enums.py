from enum import Enum


class UserRole(str, Enum):
    CHIEF = "chief"
    MEMBER = "member"


class ExpeditionStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    ACTIVE = "active"
    FINISHED = "finished"


class MemberState(str, Enum):
    INVITED = "invited"
    CONFIRMED = "confirmed"


class ExpeditionEventType(str, Enum):
    MEMBER_INVITED = "member_invited"
    MEMBER_CONFIRMED = "member_confirmed"
    EXPEDITION_STATUS = "expedition_status"
