"""Read-only confirmation guidance for Home Assistant VLAN proposals."""


def confirmation_advice(review: dict, mode: str = "balanced") -> dict:
    """Advise, never approve or execute, an administrator's VLAN proposal."""
    if mode not in ("minimal", "balanced", "cautious"):
        raise ValueError("Invalid confirmation preference")
    blocked = review.get("status") != "requires_operator_review" or bool(review.get("blockers"))
    warnings = review.get("warnings") or []
    disruptive = any(item in warnings for item in (
        "active_link_may_be_disrupted", "downstream_infrastructure_evidence"
    ))
    if blocked:
        advice = "blocked"
    elif mode == "cautious" or (mode == "balanced" and disruptive):
        advice = "confirmation_recommended"
    else:
        advice = "no_additional_confirmation_recommended"
    return {
        "confirmation_advice": advice,
        "confirmation_preference": mode,
        "authorized": False,
        "can_execute": False,
        "read_only": True,
    }
