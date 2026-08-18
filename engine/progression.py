"""Progression engine — spec.md §2 and §4.

Pure functions. No storage, no UI, no clock: `today` is always passed in so the
engine is fully deterministic and testable.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional, Sequence

from .models import (
    CapReason,
    Decision,
    Diagnosis,
    Exercise,
    ExerciseState,
    GymProfile,
    Outcome,
    SetLog,
    SetPrescription,
)
from .safety import rir_floor

# Reps as a proportion of set 1, for sets taken TO FAILURE at a fixed load.
# Source: pooled analysis of 29 studies (see evidence-base.md §11).
# Used ONLY as an anomaly band for flagging unusually steep fatigue — never as a
# prescription. Our sets are not taken to failure, so real drop-off should be
# gentler than this. Inventing prescriptive decay numbers before there is personal
# data to fit against would produce targets that are wrong for this specific user.
FAILURE_DROPOFF_BAND = [1.00, 0.70, 0.55, 0.50, 0.45]

LAYOFF_DAYS = 14
LAYOFF_DROP = 0.10        # express as the DROP, not 1-drop: 1-0.9 is 0.09999...
STALL_DROP = 0.10         # (same floating-point trap)
STALL_THRESHOLD = 3
FATIGUE_PATIENCE = 2       # tolerate transient fatigue this many sessions before
                           # progressing on set 1's merit anyway
RIR_TRUST_CAP = 3          # RIR 4+ is close to noise (Remmert et al. 2023)


# ---------------------------------------------------------------- helpers


def round_to_increment(weight: float, increment: float, *, down: bool = False) -> float:
    if increment <= 0:
        return round(weight, 2)
    steps = weight / increment
    steps = int(steps) if down else round(steps)
    return round(steps * increment, 2)


def rir_ramp(num_sets: int) -> List[int]:
    """Target RIR per set — further from failure early, closest on the last set.

    Taking set 1 to failure costs ~30% of set 2 and ~45% of set 3. Since weekly
    volume is the primary hypertrophy driver, buying failure on set 1 at the price
    of sets 2 and 3 is plausibly a net loss.
    """
    if num_sets <= 0:
        return []
    if num_sets == 1:
        return [0]
    if num_sets == 2:
        return [1, 0]
    return [2] + [1] * (num_sets - 2) + [0]


def working_sets(sets: Sequence[SetLog]) -> List[SetLog]:
    return sorted((s for s in sets if not s.is_warmup), key=lambda s: s.set_index)


# ---------------------------------------------------------------- prescribe


def prescribe(
    exercise: Exercise,
    state: Optional[ExerciseState],
    num_sets: int,
    gym: GymProfile,
    spotter_present: bool,
    today: date,
) -> List[SetPrescription]:
    """Build this session's plan. Returns [] for a first-ever exercise — log freely,
    prescriptions begin at session two."""
    if state is None:
        return []

    weight = state.current_weight
    reps = state.current_rep_target
    notes_deload = False

    if state.last_performed_date is not None:
        if (today - state.last_performed_date) > timedelta(days=LAYOFF_DAYS):
            drop = round_to_increment(
                weight * LAYOFF_DROP, exercise.load_increment, down=True
            )
            weight = round(weight - max(drop, exercise.load_increment), 2)
            notes_deload = True

    floor, cap_reason, _advice = rir_floor(exercise, gym, spotter_present)
    ramp = rir_ramp(num_sets)

    plan: List[SetPrescription] = []
    for i, natural_rir in enumerate(ramp):
        effective_rir = max(natural_rir, floor)
        capped = effective_rir > natural_rir
        plan.append(
            SetPrescription(
                set_index=i + 1,
                target_weight=weight,
                # v1 prescribes flat rep targets. Later-set shortfall is recorded and
                # diagnosed, never penalised. Fitted per-set decay lands in v1.1 once
                # there is real training history to regress against.
                target_reps=reps,
                target_rir=effective_rir,
                capped=capped,
                cap_reason=cap_reason if capped else CapReason.NONE,
                rest_seconds=exercise.default_rest_seconds,
            )
        )

    if notes_deload:
        for p in plan:
            p.rest_seconds = exercise.default_rest_seconds
    return plan


# ---------------------------------------------------------------- classify


def classify(sets: Sequence[SetLog]) -> Outcome:
    ws = working_sets(sets)
    if not ws:
        return Outcome.FIRST_TIME

    first = ws[0]
    if first.reps < first.target_reps or first.weight < first.target_weight:
        return Outcome.MISS

    for s in ws[1:]:
        if s.reps < s.target_reps or s.weight < s.target_weight:
            return Outcome.PARTIAL
    return Outcome.HIT


def dropoff_notes(sets: Sequence[SetLog]) -> List[str]:
    """Flag fatigue steeper than the to-failure literature band. Since our sets stop
    short of failure, falling below that band is genuinely unusual."""
    ws = working_sets(sets)
    notes: List[str] = []
    if len(ws) < 2 or ws[0].reps == 0:
        return notes

    base = ws[0].reps
    for s in ws[1:]:
        idx = s.set_index - 1
        if idx >= len(FAILURE_DROPOFF_BAND):
            continue
        ratio = s.reps / base
        if ratio < FAILURE_DROPOFF_BAND[idx]:
            notes.append(
                f"Set {s.set_index} fell to {ratio:.0%} of set 1 — steeper than typical "
                f"even for sets taken to failure. Try longer rest before cutting the load."
            )
    return notes


# ---------------------------------------------------------------- progress


def _condition_rir(s: SetLog) -> tuple[int, bool]:
    """Returns (rir_used, treat_as_had_more).

    A capped RIR 1 means "I had more and was told to stop" -> progress.
    An uncapped RIR 1 means "that was nearly everything" -> hold.
    Identical logged value, opposite correct action.
    """
    if s.stopped_at_cap:
        return 1, True
    if s.rir is None:
        return 2, False
    return min(s.rir, RIR_TRUST_CAP), False


def progress(
    exercise: Exercise,
    state: ExerciseState,
    sets: Sequence[SetLog],
    today: date,
) -> Decision:
    ws = working_sets(sets)
    if not ws:
        return Decision(
            diagnosis=Diagnosis.FIRST_TIME,
            next_weight=state.current_weight,
            next_rep_target=state.current_rep_target,
            consecutive_stalls=state.consecutive_stalls,
            message="No working sets logged.",
        )

    first = ws[0]
    outcome = classify(ws)
    lo, hi = exercise.rep_range
    inc = 0.0 if (exercise.is_bodyweight and first.weight == 0) else exercise.load_increment
    weight = first.target_weight or first.weight
    reps = first.target_reps or state.current_rep_target
    stalls = state.consecutive_stalls
    notes = dropoff_notes(ws)

    # --- set 1 missed: the load is too heavy. This is the only strength signal.
    if outcome == Outcome.MISS:
        stalls += 1
        if stalls >= STALL_THRESHOLD:
            options = [
                f"Drop to {round(weight - max(round_to_increment(weight * STALL_DROP, inc or 2.5, down=True), inc or 2.5), 2)} and rebuild"
            ]
            if exercise.substitutes:
                options.append(f"Swap to: {', '.join(exercise.substitutes)}")
            return Decision(
                diagnosis=Diagnosis.STALL_INTERVENTION,
                next_weight=weight,
                next_rep_target=reps,
                consecutive_stalls=stalls,
                message=(
                    f"Stalled {stalls} sessions on {exercise.name}. Pick an intervention — "
                    "nothing is applied automatically."
                ),
                notes=notes,
                intervention_options=options,
            )
        return Decision(
            diagnosis=Diagnosis.REPEAT_TOO_HEAVY,
            next_weight=weight,
            next_rep_target=reps,
            consecutive_stalls=stalls,
            message=f"Set 1 fell short — repeat {weight} for {reps}. Stall {stalls}/{STALL_THRESHOLD}.",
            notes=notes,
        )

    # --- set 1 hit, later sets faded: fatigue or recovery, NOT strength.
    # Do not cut the load and do not count a stall. Cutting weight here is the
    # standard failure mode of existing apps when the real cause was short rest.
    if outcome == Outcome.PARTIAL:
        fatigue = state.consecutive_fatigue + 1
        if fatigue <= FATIGUE_PATIENCE:
            return Decision(
                diagnosis=Diagnosis.REPEAT_FATIGUE,
                next_weight=weight,
                next_rep_target=reps,
                consecutive_stalls=stalls,
                consecutive_fatigue=fatigue,
                message=(
                    f"Set 1 hit but later sets faded on {exercise.name}. That is fatigue, not "
                    f"a strength problem — hold {weight} and lengthen rest before cutting load."
                ),
                notes=notes,
            )
        # Persistent, not transient. Set 1 keeps clearing its target, so the lifter IS
        # getting stronger; it is the flat later-set targets that are unrealistic. Fall
        # through and progress on set 1's merit rather than holding forever.
        notes.append(
            f"Later sets have faded {fatigue} sessions running while set 1 kept hitting. "
            "That is normal within-session fatigue, not a plateau — progressing on set 1 "
            "and relaxing the later-set targets."
        )
        notes.append(
            "This is the case fitted per-set decay targets are meant to handle properly "
            "(v1.1); flat targets across sets cannot represent it."
        )

    # --- clean hit. Read effort from set 1 and progress.
    stalls = 0
    rir_used, had_more = _condition_rir(first)

    if had_more:
        notes.append("Set 1 was cap-limited, so its RIR is a ceiling, not a true effort reading.")
        rir_used = 2

    if rir_used == 0:
        notes.append(
            "Set 1 reached failure — that costs reps on every later set. The target was "
            "set too aggressively; holding here rather than adding load."
        )
        return Decision(
            diagnosis=Diagnosis.HOLD_CONSOLIDATE,
            next_weight=weight,
            next_rep_target=reps,
            consecutive_stalls=stalls,
            consecutive_fatigue=0,
            message=f"Hold {weight} × {reps}. Consolidate before progressing.",
            notes=notes,
        )

    step = 2 if rir_used >= RIR_TRUST_CAP else 1

    if reps + step <= hi:
        if rir_used >= RIR_TRUST_CAP:
            # Only true on this branch — saying it while adding load contradicts itself.
            notes.append(
                "Reported RIR 3+ is low-confidence, so moving by reps rather than a "
                "load jump."
            )
        return Decision(
            diagnosis=Diagnosis.PROGRESS_REPS,
            next_weight=weight,
            next_rep_target=reps + step,
            consecutive_stalls=stalls,
            consecutive_fatigue=0,
            message=f"Next time: {weight} × {reps + step}.",
            notes=notes,
        )

    if inc == 0.0:
        # Bodyweight with no added load — keep extending reps past the range.
        return Decision(
            diagnosis=Diagnosis.PROGRESS_REPS,
            next_weight=weight,
            next_rep_target=reps + step,
            consecutive_stalls=stalls,
            consecutive_fatigue=0,
            message=f"Next time: bodyweight × {reps + step}.",
            notes=notes,
        )

    # Add the increment to the CURRENT weight — do not re-round onto an absolute grid.
    # 135 lb is loadable (45 bar + two 45s) but is not a multiple of the 10 lb jump, so
    # snapping 145 to the nearest multiple of 10 silently gave back 5 lb every cycle.
    # The weight you are already lifting is by definition achievable; current + increment
    # therefore is too.
    new_weight = round(weight + inc, 2)
    return Decision(
        diagnosis=Diagnosis.PROGRESS_LOAD,
        next_weight=new_weight,
        next_rep_target=lo,
        consecutive_stalls=stalls,
        consecutive_fatigue=0,
        message=f"Top of the rep range — next time: {new_weight} × {lo}.",
        notes=notes,
    )


def apply(state: ExerciseState, decision: Decision, today: date) -> ExerciseState:
    """Fold a decision back into state. Never called for STALL_INTERVENTION until
    the user picks an option."""
    return ExerciseState(
        exercise_id=state.exercise_id,
        current_weight=decision.next_weight,
        current_rep_target=decision.next_rep_target,
        consecutive_stalls=decision.consecutive_stalls,
        consecutive_fatigue=decision.consecutive_fatigue,
        last_performed_date=today,
        observed_dropoff=state.observed_dropoff,
    )


def bootstrap(exercise: Exercise, first_log: SetLog, today: date) -> ExerciseState:
    """Turn a first-ever logged set into a real ExerciseState.

    prescribe() returns [] when state is None — log freely, no targets — but nothing
    else in the engine turns that first log into a state for prescribe() to build on
    next time. This is the missing other half of that contract: weight carries over
    exactly as lifted, reps clamp into the exercise's rep_range so a lifter who did
    20 reps on their first try doesn't get prescribed 20 reps forever, and a lifter
    who did 2 doesn't get treated as already at range floor with room to spare."""
    lo, hi = exercise.rep_range
    reps = max(lo, min(first_log.reps, hi))
    return ExerciseState(
        exercise_id=exercise.id,
        current_weight=first_log.weight,
        current_rep_target=reps,
        last_performed_date=today,
    )
