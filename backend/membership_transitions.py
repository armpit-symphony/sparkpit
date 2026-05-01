from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from backend.membership_states import MembershipState, is_active_membership, normalize_membership_state


@dataclass(frozen=True)
class MembershipTransition:
    user_id: str
    from_state: MembershipState
    to_state: MembershipState
    actor_type: str = "system"
    actor_id: str = "system"
    reason: str = "scaffold_transition"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MembershipTransitionResult:
    allowed: bool
    reason: str
    transition: MembershipTransition


def evaluate_transition(
    user_id: str,
    from_state: Optional[str],
    to_state: Optional[str],
    actor_type: str = "system",
    actor_id: str = "system",
    metadata: Optional[Dict[str, Any]] = None,
) -> MembershipTransitionResult:
    """
    Transition helper skeleton.

    Business-policy enforcement is intentionally not finalized here yet.
    """

    transition = MembershipTransition(
        user_id=user_id,
        from_state=normalize_membership_state(from_state),
        to_state=normalize_membership_state(to_state),
        actor_type=actor_type,
        actor_id=actor_id,
        metadata=metadata or {},
    )
    reason = "no_state_change" if transition.from_state == transition.to_state else "policy_not_enforced_yet"
    return MembershipTransitionResult(allowed=True, reason=reason, transition=transition)


def build_membership_transition_payload(result: MembershipTransitionResult) -> Dict[str, Any]:
    return {
        "user_id": result.transition.user_id,
        "from_state": result.transition.from_state.value,
        "to_state": result.transition.to_state.value,
        "allowed": result.allowed,
        "reason": result.reason,
        "actor_type": result.transition.actor_type,
        "actor_id": result.transition.actor_id,
        "metadata": result.transition.metadata,
    }


def require_active_member_stub(user: Dict[str, Any]) -> Dict[str, Any]:
    if not is_active_membership(user.get("membership_status")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership not active")
    return user
