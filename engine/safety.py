"""Safety layer — spec.md §3. Ships in v1, not deferred.

The engine's core mechanic is prescribing proximity to failure, and losing control
of a load is the dominant mechanism in ED-presenting weight training injuries
(65.5%, Kerr et al. 2010; 90.4% free weights). A prescription of RIR 0 on barbell
bench for a lifter training alone is a hazard the app itself created.
"""

from __future__ import annotations

from typing import Tuple

from .models import CapReason, Exercise, FailureRisk, GymProfile


def rir_floor(
    exercise: Exercise,
    gym: GymProfile,
    spotter_present: bool,
) -> Tuple[int, CapReason, str]:
    """Return (floor, reason, advice).

    Resolution order is deliberate: rack safeties rank ABOVE a spotter. Pins at
    chest height solve the problem permanently and are always available; a spotter
    is a variable the lifter does not control.
    """
    if exercise.failure_risk == FailureRisk.SAFE_TO_FAILURE:
        return 0, CapReason.NONE, ""

    if spotter_present:
        return 0, CapReason.NONE, ""

    if exercise.failure_risk == FailureRisk.NEEDS_SAFETIES:
        if gym.has_rack_safeties:
            return 0, CapReason.NONE, "Set the rack pins at chest height before you start."
        advice = (
            f"Training alone on {exercise.name} with no safeties — capped at RIR 1. "
            "Setting rack pins removes this cap entirely at no cost to the stimulus."
        )
        if exercise.substitutes:
            advice += f" Safer alternatives: {', '.join(exercise.substitutes)}."
        return 1, CapReason.SOLO_NO_SAFETIES, advice

    # BAILOUT_POSSIBLE — failing is survivable with technique.
    return 0, CapReason.SOLO_BAILOUT, (
        f"Training alone on {exercise.name}. Failing is recoverable, but know how to "
        "bail before your last set."
    )
