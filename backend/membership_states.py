from enum import Enum
from typing import Optional


class MembershipState(str, Enum):
    """Centralized membership-state enum used across auth and policy checks."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    CANCELED = "canceled"


DEFAULT_MEMBERSHIP_STATE = MembershipState.PENDING


def normalize_membership_state(value: Optional[str]) -> MembershipState:
    if isinstance(value, MembershipState):
        return value
    if not value:
        return DEFAULT_MEMBERSHIP_STATE
    normalized = str(value).strip().lower()
    for state in MembershipState:
        if normalized == state.value:
            return state
    return DEFAULT_MEMBERSHIP_STATE


def is_active_membership(value: Optional[str]) -> bool:
    return normalize_membership_state(value) == MembershipState.ACTIVE
