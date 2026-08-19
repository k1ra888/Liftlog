"""Exercise library with equipment-derived defaults — spec.md §1.

Design principle: asking a user to fill in eight metadata fields per exercise is a
form nobody completes, least of all standing in a gym. So a custom exercise asks for
three things — name, muscles, equipment — and everything else is derived from the
equipment type. All derived values remain editable.

Increments below are calibrated to THIS gym: smallest plate 5 lb, no microplates.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Tuple

from .models import Equipment, Exercise, FailureRisk


# Gym-specific presets. `increment` is the smallest jump ACTUALLY achievable —
# not the smallest plate. Standardized to 5 lb everywhere: with 2.5 lb plates
# available, a symmetric barbell/Smith load (one 2.5 per side) moves in 5 lb
# steps, not 10 — the earlier "5 lb smallest plate -> 10 lb barbell steps" premise
# was wrong for this gym. Dumbbells and cable stacks were already 5 lb.
PRESETS: Dict[str, dict] = {
    "smith": {
        "equipment": Equipment.BARBELL,
        "increment": 5.0,               # 2.5 lb plate per side
        "failure_risk": FailureRisk.BAILOUT_POSSIBLE,   # rotate the bar to rack it anywhere
        "rest": 150,
        "rep_range": (6, 10),
    },
    "barbell": {
        "equipment": Equipment.BARBELL,
        "increment": 5.0,               # 2.5 lb plate per side
        "failure_risk": FailureRisk.NEEDS_SAFETIES,
        "rest": 150,
        "rep_range": (6, 10),
    },
    "dumbbell": {
        "equipment": Equipment.DUMBBELL,
        "increment": 5.0,               # per dumbbell, as written on the rack
        "failure_risk": FailureRisk.BAILOUT_POSSIBLE,
        "rest": 120,
        "rep_range": (8, 12),
    },
    "fixed_bar": {
        "equipment": Equipment.BARBELL,
        "increment": 5.0,
        "failure_risk": FailureRisk.BAILOUT_POSSIBLE,
        "rest": 120,
        # Kept wide even at 5 lb (10% of a 50 lb bar, gentler than the 20% this was
        # originally sized for): pre-loaded bars still typically skip weights, and
        # Schoenfeld et al. — any range >= ~30% 1RM grows muscle — means there's no
        # cost to keeping the buffer.
        "rep_range": (8, 15),
    },
    "cable": {
        "equipment": Equipment.CABLE,
        "increment": 5.0,               # stack pin; confirmed at the gym across cable machines
        "failure_risk": FailureRisk.SAFE_TO_FAILURE,
        "rest": 90,
        "rep_range": (10, 15),
    },
    "machine": {
        "equipment": Equipment.MACHINE,
        "increment": 5.0,
        "failure_risk": FailureRisk.SAFE_TO_FAILURE,
        "rest": 90,
        "rep_range": (10, 15),
    },
    "bodyweight": {
        "equipment": Equipment.BODYWEIGHT,
        "increment": 5.0,
        "failure_risk": FailureRisk.SAFE_TO_FAILURE,
        "rest": 120,
        "rep_range": (5, 12),
    },
}


def make_exercise(
    id: str,
    name: str,
    preset: str,
    primary: Sequence[str],
    secondary: Sequence[str] = (),
    *,
    rep_range: Optional[Tuple[int, int]] = None,
    increment: Optional[float] = None,
    failure_risk: Optional[FailureRisk] = None,
    rest_seconds: Optional[int] = None,
    substitutes: Sequence[str] = (),
) -> Exercise:
    """Build an exercise from an equipment preset. Every derived field can be
    overridden — this is what the app's 'add your own exercise' flow calls."""
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; options: {sorted(PRESETS)}")
    p = PRESETS[preset]
    return Exercise(
        id=id,
        name=name,
        primary_muscles=tuple(primary),
        secondary_muscles=tuple(secondary),
        rep_range=rep_range or p["rep_range"],
        load_increment=increment if increment is not None else p["increment"],
        equipment=p["equipment"],
        failure_risk=failure_risk or p["failure_risk"],
        substitutes=tuple(substitutes),
        default_rest_seconds=rest_seconds or p["rest"],
        is_bodyweight=(p["equipment"] == Equipment.BODYWEIGHT),
    )


# --------------------------------------------------------------- seeded routine
# Push day, as actually trained.

PUSH_DAY = [
    make_exercise(
        "smith_bench", "Smith Machine Bench", "smith",
        primary=["chest", "front delts"], secondary=["triceps"],
        substitutes=["Dumbbell Bench"],
    ),
    make_exercise(
        "db_bench", "Dumbbell Bench", "dumbbell",
        primary=["chest", "front delts"], secondary=["triceps"],
        substitutes=["Smith Machine Bench"],
    ),
    make_exercise(
        "smith_incline", "Smith Machine Incline", "smith",
        primary=["chest", "front delts"], secondary=["triceps"],
        substitutes=["Dumbbell Incline"],
    ),
    make_exercise(
        "db_incline", "Dumbbell Incline", "dumbbell",
        primary=["chest", "front delts"], secondary=["triceps"],
        substitutes=["Smith Machine Incline"],
    ),
    make_exercise(
        "standing_ohp_bar", "Standing Shoulder Press (fixed bar)", "fixed_bar",
        primary=["front delts"], secondary=["triceps", "side delts"],
    ),
    make_exercise(
        "cable_oh_tricep", "Overhead Tricep Extension (rope)", "cable",
        primary=["triceps"],
    ),
    make_exercise(
        "cable_pushdown_bar", "Tricep Pushdown (bar)", "cable",
        primary=["triceps"],
    ),
]

# --------------------------------------------------------------- full catalog
# A pick-from-this list, not a prescribed routine — lets the user add/remove from
# their actual routine against real fractional-volume numbers instead of guesswork,
# and means custom exercises aren't the only path to a properly-tagged Exercise.
# Every entry here carries primary/secondary muscles for weekly_volume() and an
# equipment preset for load_increment/failure_risk/rep_range, exactly like PUSH_DAY.
#
# Left out on purpose: isometric holds (planks, static carries). The whole model
# is weight x reps x RIR; a hold doesn't have reps to progress, so it doesn't fit
# without a second mechanic. Revisit if that mechanic ever gets built.

# Push-day candidates NOT currently in the routine — chest/shoulder/triceps moves
# the owner can add or swap in. Barbell entries deliberately included even though
# solo training caps their RIR (safety.py) — that's the safety floor doing its job,
# not a reason to leave them out of the picker.
PUSH_EXTRA = [
    make_exercise(
        "barbell_bench", "Barbell Bench Press", "barbell",
        primary=["chest", "front delts"], secondary=["triceps"],
        substitutes=["Dumbbell Bench", "Smith Machine Bench"],
    ),
    make_exercise(
        "pec_deck_fly", "Pec Deck / Chest Fly (machine)", "machine",
        primary=["chest"],
        substitutes=["Cable Chest Fly"],
    ),
    make_exercise(
        "cable_fly", "Cable Chest Fly", "cable",
        primary=["chest"],
        substitutes=["Pec Deck / Chest Fly (machine)"],
    ),
    make_exercise(
        "barbell_ohp", "Barbell Overhead Press", "barbell",
        primary=["front delts"], secondary=["triceps", "side delts"],
        failure_risk=FailureRisk.BAILOUT_POSSIBLE,   # bar bails forward, not pinned like bench
        substitutes=["Standing Shoulder Press (fixed bar)", "Seated Dumbbell Shoulder Press"],
    ),
    make_exercise(
        "db_shoulder_press", "Seated Dumbbell Shoulder Press", "dumbbell",
        primary=["front delts"], secondary=["triceps", "side delts"],
        substitutes=["Standing Shoulder Press (fixed bar)"],
    ),
    make_exercise(
        "machine_shoulder_press", "Machine Shoulder Press", "machine",
        primary=["front delts"], secondary=["triceps", "side delts"],
    ),
    make_exercise(
        "db_lateral_raise", "Dumbbell Lateral Raise", "dumbbell",
        primary=["side delts"],
        substitutes=["Cable Lateral Raise"],
    ),
    make_exercise(
        "cable_lateral_raise", "Cable Lateral Raise", "cable",
        primary=["side delts"],
        substitutes=["Dumbbell Lateral Raise"],
    ),
    make_exercise(
        "ezbar_skull_crusher", "EZ-Bar Skull Crusher", "fixed_bar",
        primary=["triceps"],
    ),
]

PUSH_EXERCISES = PUSH_DAY + PUSH_EXTRA

PULL_EXERCISES = [
    make_exercise(
        "lat_pulldown", "Lat Pulldown", "cable",
        primary=["lats"], secondary=["biceps", "upper back"],
        substitutes=["Pull-Up"],
    ),
    make_exercise(
        "pullup", "Pull-Up", "bodyweight",
        primary=["lats"], secondary=["biceps"],
        substitutes=["Lat Pulldown"],
    ),
    make_exercise(
        "seated_cable_row", "Seated Cable Row", "cable",
        primary=["upper back"], secondary=["lats", "biceps"],
        substitutes=["Chest-Supported Row", "Single-Arm Seated Cable Row"],
    ),
    make_exercise(
        "single_arm_seated_row", "Single-Arm Seated Cable Row", "cable",
        primary=["upper back"], secondary=["lats", "biceps"],
        substitutes=["Seated Cable Row"],
    ),
    make_exercise(
        "chest_supported_row", "Chest-Supported Row (machine)", "machine",
        primary=["upper back"], secondary=["lats", "biceps"],
        substitutes=["Seated Cable Row"],
    ),
    make_exercise(
        "smith_row", "Smith Machine Bent-Over Row", "smith",
        primary=["upper back"], secondary=["lats", "biceps"],
    ),
    make_exercise(
        "face_pull", "Face Pull (cable)", "cable",
        primary=["side delts"], secondary=["upper back"],
    ),
    make_exercise(
        "reverse_pec_deck", "Reverse Pec Deck", "machine",
        primary=["side delts"], secondary=["upper back"],
        substitutes=["Face Pull (cable)"],
    ),
    make_exercise(
        "db_curl", "Dumbbell Bicep Curl", "dumbbell",
        primary=["biceps"],
    ),
    make_exercise(
        "cable_curl", "Cable Bicep Curl", "cable",
        primary=["biceps"],
        substitutes=["Dumbbell Bicep Curl"],
    ),
    make_exercise(
        "preacher_curl_machine", "Preacher Curl (machine)", "machine",
        primary=["biceps"],
    ),
    make_exercise(
        "db_shrug", "Dumbbell Shrug", "dumbbell",
        primary=["traps"], secondary=["upper back"],
    ),
]

LEG_EXERCISES = [
    make_exercise(
        "leg_press", "Leg Press (machine)", "machine",
        primary=["quads"], secondary=["glutes"],
        substitutes=["Hack Squat", "Smith Machine Squat"],
    ),
    make_exercise(
        "hack_squat", "Hack Squat (machine)", "machine",
        primary=["quads"], secondary=["glutes"],
        substitutes=["Leg Press (machine)"],
    ),
    make_exercise(
        "smith_squat", "Smith Machine Squat", "smith",
        primary=["quads"], secondary=["glutes"],
        substitutes=["Leg Press (machine)"],
    ),
    make_exercise(
        "leg_extension", "Leg Extension (machine)", "machine",
        primary=["quads"],
    ),
    make_exercise(
        "leg_curl_machine", "Leg Curl (machine)", "machine",
        primary=["hamstrings"],
    ),
    make_exercise(
        "db_rdl", "Dumbbell Romanian Deadlift", "dumbbell",
        primary=["hamstrings"], secondary=["glutes"],
    ),
    make_exercise(
        "hip_thrust_machine", "Hip Thrust (machine)", "machine",
        primary=["glutes"], secondary=["hamstrings"],
    ),
    make_exercise(
        "walking_lunge_db", "Dumbbell Walking Lunge", "dumbbell",
        primary=["quads"], secondary=["glutes"],
    ),
    make_exercise(
        "standing_calf_raise", "Standing Calf Raise (machine)", "machine",
        primary=["calves"],
        substitutes=["Calf Raise (hack squat machine)", "Seated Calf Raise (machine)"],
    ),
    make_exercise(
        "seated_calf_raise", "Seated Calf Raise (machine)", "machine",
        primary=["calves"],
        substitutes=["Calf Raise (hack squat machine)", "Standing Calf Raise (machine)"],
    ),
    make_exercise(
        "calf_raise_hack_squat", "Calf Raise (hack squat machine)", "machine",
        primary=["calves"],
        substitutes=["Standing Calf Raise (machine)", "Seated Calf Raise (machine)"],
    ),
]

CORE_EXERCISES = [
    make_exercise(
        "cable_crunch", "Cable Crunch", "cable",
        primary=["abs"],
    ),
    make_exercise(
        "hanging_leg_raise", "Hanging Leg Raise", "bodyweight",
        primary=["abs"],
    ),
]

EXERCISE_LIBRARY: list = PUSH_EXERCISES + PULL_EXERCISES + LEG_EXERCISES + CORE_EXERCISES
EXERCISE_BY_ID: dict = {ex.id: ex for ex in EXERCISE_LIBRARY}

# --------------------------------------------------------------- pull / legs, as described
# Same status as PUSH_DAY: the owner's actual routine, picked from the catalog above.

PULL_DAY = [
    EXERCISE_BY_ID["lat_pulldown"],
    EXERCISE_BY_ID["seated_cable_row"],
    EXERCISE_BY_ID["single_arm_seated_row"],
    EXERCISE_BY_ID["preacher_curl_machine"],
]

LEG_DAY = [
    EXERCISE_BY_ID["hack_squat"],
    EXERCISE_BY_ID["leg_extension"],
    EXERCISE_BY_ID["leg_curl_machine"],
    EXERCISE_BY_ID["calf_raise_hack_squat"],
]

# PUSH_DAY lists BOTH equipment alternates for bench and incline (Smith and
# dumbbell) because the owner alternates between them session to session — he never
# does both in one sitting. Volume math needs a single actual session, not the full
# menu, or bench/incline get double-counted. This picks one of each alternating
# pair; swap in the db_* id here if you want the numbers for the other variant.
PUSH_DAY_SESSION = [
    EXERCISE_BY_ID["smith_bench"],
    EXERCISE_BY_ID["smith_incline"],
    EXERCISE_BY_ID["standing_ohp_bar"],
    EXERCISE_BY_ID["cable_oh_tricep"],
    EXERCISE_BY_ID["cable_pushdown_bar"],
]

ROTATION = ["push", "pull", "legs", "rest"]


def next_in_rotation(last: Optional[str]) -> str:
    """The split is a rotation, not a calendar. Miss a day and the rotation simply
    resumes — it does not decide you 'skipped leg day Tuesday'."""
    if last is None or last not in ROTATION:
        return ROTATION[0]
    return ROTATION[(ROTATION.index(last) + 1) % len(ROTATION)]


def weekly_volume(
    logged: Sequence[Tuple[Exercise, int]],
) -> Dict[str, float]:
    """Fractional set counting — direct sets 1.0, indirect 0.5 (Pelland et al.).
    `logged` is [(exercise, number_of_working_sets), ...]."""
    out: Dict[str, float] = {}
    for ex, n in logged:
        for m in ex.primary_muscles:
            out[m] = out.get(m, 0.0) + 1.0 * n
        for m in ex.secondary_muscles:
            out[m] = out.get(m, 0.0) + 0.5 * n
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ------------------------------------------------------------- "the numbers"
# Muscle-balance view across a full rotation, not a single day. Pelland et al.'s
# fractional counting is a weekly-volume finding; in a rotation (not calendar) split
# the equivalent unit is one full pass through push/pull/legs, since "rest" is by
# definition zero exercises. No MEV/MRV lines here (spec.md Tier 3, unvalidated) —
# counts only, same restriction weekly_volume() already carries.


def rotation_volume(
    logged_by_day: Dict[str, Sequence[Tuple[Exercise, int]]],
) -> Dict[str, float]:
    """Combine per-day (exercise, working_sets) pairs into one rotation-wide
    fractional-volume balance. Deliberately takes the same shape weekly_volume()
    does, per day, so this works identically whether `logged_by_day` holds a
    routine preview (assumed set counts) or real logged history summed by day —
    the UI's "numbers" view is the same call either way, just different input."""
    combined: List[Tuple[Exercise, int]] = []
    for day, entries in logged_by_day.items():
        if day not in ROTATION:
            raise ValueError(f"unknown rotation day {day!r}; options: {ROTATION}")
        combined.extend(entries)
    return weekly_volume(combined)


def routine_preview(sets_per_exercise: int = 3) -> Dict[str, float]:
    """Muscle balance implied by the current routine, assuming a flat
    `sets_per_exercise` since no session history exists yet. This is a preview, not
    a prescription — once real sets are logged, call rotation_volume() with actual
    per-exercise counts instead of guessing at this default.

    Uses PUSH_DAY_SESSION rather than PUSH_DAY: the latter includes both alternates
    of bench and incline, which are never performed in the same session."""
    return rotation_volume({
        "push": [(ex, sets_per_exercise) for ex in PUSH_DAY_SESSION],
        "pull": [(ex, sets_per_exercise) for ex in PULL_DAY],
        "legs": [(ex, sets_per_exercise) for ex in LEG_DAY],
    })
