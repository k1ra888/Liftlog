"""Data model for the progression engine.

Mirrors spec.md §1. Pure data — no storage, no UI, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional, Tuple


class Equipment(str, Enum):
    BARBELL = "barbell"
    DUMBBELL = "dumbbell"
    MACHINE = "machine"
    CABLE = "cable"
    BODYWEIGHT = "bodyweight"


class FailureRisk(str, Enum):
    """What happens if you fail a rep. Drives the safety floor (spec §3)."""

    SAFE_TO_FAILURE = "safe_to_failure"       # machines, cables, leg press
    BAILOUT_POSSIBLE = "bailout_possible"     # dumbbells, Smith, goblet squat
    NEEDS_SAFETIES = "needs_safeties"         # barbell bench / squat / OHP


class CapReason(str, Enum):
    NONE = "none"
    SOLO_NO_SAFETIES = "solo_no_safeties"
    SOLO_BAILOUT = "solo_bailout"


@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    primary_muscles: Tuple[str, ...]          # weighted 1.0 toward volume
    secondary_muscles: Tuple[str, ...] = ()   # weighted 0.5 (Pelland et al.)
    rep_range: Tuple[int, int] = (8, 12)
    load_increment: float = 2.5               # smallest jump ACTUALLY available
    equipment: Equipment = Equipment.BARBELL
    failure_risk: FailureRisk = FailureRisk.SAFE_TO_FAILURE
    substitutes: Tuple[str, ...] = ()         # safer same-muscle alternatives
    default_rest_seconds: int = 120
    is_bodyweight: bool = False


@dataclass
class GymProfile:
    has_rack_safeties: bool = False
    has_smith_machine: bool = False
    dumbbell_max: Optional[float] = None


@dataclass
class SetPrescription:
    """What the engine tells you to do for one set."""

    set_index: int
    target_weight: float
    target_reps: int
    target_rir: int
    capped: bool = False                      # floor raised this set's RIR
    cap_reason: CapReason = CapReason.NONE
    rest_seconds: int = 120


@dataclass
class SetLog:
    """What actually happened. target_* fields carry the prescription forward —
    without them you cannot tell a hit from a miss."""

    set_index: int
    weight: float
    reps: int
    rir: Optional[int] = None
    target_weight: float = 0.0
    target_reps: int = 0
    target_rir: int = 0
    stopped_at_cap: bool = False
    is_warmup: bool = False


@dataclass
class ExerciseState:
    exercise_id: str
    current_weight: float
    current_rep_target: int
    consecutive_stalls: int = 0
    consecutive_fatigue: int = 0                     # set 1 hit, later sets faded
    last_performed_date: Optional[date] = None
    observed_dropoff: Optional[List[float]] = None   # fitted in v1.1; None in v1


class Outcome(str, Enum):
    HIT = "hit"
    PARTIAL = "partial"       # set 1 hit, later set fell short
    MISS = "miss"             # set 1 fell short
    FIRST_TIME = "first_time"


class Diagnosis(str, Enum):
    PROGRESS_REPS = "progress_reps"
    PROGRESS_LOAD = "progress_load"
    HOLD_CONSOLIDATE = "hold_consolidate"
    REPEAT_TOO_HEAVY = "repeat_too_heavy"          # set 1 missed
    REPEAT_FATIGUE = "repeat_fatigue"              # set 1 hit, later sets faded
    STALL_INTERVENTION = "stall_intervention"
    FIRST_TIME = "first_time"


@dataclass
class Decision:
    diagnosis: Diagnosis
    next_weight: float
    next_rep_target: int
    consecutive_stalls: int
    message: str
    consecutive_fatigue: int = 0
    notes: List[str] = field(default_factory=list)
    intervention_options: List[str] = field(default_factory=list)
