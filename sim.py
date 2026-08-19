"""Readable walkthrough of the engine — no phone, no UI, no IDE required.

Simulates a lifter with a real strength ceiling and within-session fatigue, then
prints every prescription and the reasoning behind it. This is how you sanity-check
the decisions before an interface exists to hide them.

Run:  python sim.py
"""

from datetime import date, timedelta

from engine import (
    CALIBRATION_MAX_SETS,
    CalibrationRating,
    Equipment, Exercise, ExerciseState, FailureRisk, GymProfile, SetLog,
    apply, bootstrap, calibrate_step, calibration_target_reps, make_exercise,
    prescribe, progress,
)

# Your gym: 5 lb smallest plate, so the Smith bar moves in 10 lb steps.
SMITH_BENCH = make_exercise(
    "smith_bench", "Smith Machine Bench", "smith",
    primary=["chest", "front delts"], secondary=["triceps"],
    substitutes=["Dumbbell Bench"],
)

# A free barbell for contrast — this is the one the safety layer actually binds on.
BARBELL_BENCH = make_exercise(
    "barbell_bench", "Barbell Bench Press", "barbell",
    primary=["chest", "front delts"], secondary=["triceps"],
    substitutes=["Dumbbell Bench", "Smith Machine Bench"],
)


def make_lifter(true_max_at_6: float):
    """Returns a function producing (reps_completed, rir) for a given set.

    The lifter stops when they hit the prescription rather than grinding out extras,
    and loses capacity across sets within the session.
    """
    dropoff = [1.0, 0.88, 0.78]

    def perform(weight: float, set_index: int, target_reps: int):
        capacity_at_weight = 6 + (true_max_at_6 - weight) / 10.0 * 2.0
        capacity = capacity_at_weight * dropoff[min(set_index - 1, len(dropoff) - 1)]
        achievable = max(0, int(capacity))
        done = min(achievable, target_reps)
        return done, min(max(0, achievable - done), 4)

    return perform


def run(exercise: Exercise, start_lb: float, ceiling_lb: float, sessions: int,
        *, rack_safeties: bool, spotter: bool = False) -> None:
    gym = GymProfile(has_rack_safeties=rack_safeties)
    state = ExerciseState(exercise.id, start_lb, exercise.rep_range[0],
                          last_performed_date=date(2026, 8, 15))
    perform = make_lifter(ceiling_lb)
    day = date(2026, 8, 15)

    if exercise.failure_risk == FailureRisk.NEEDS_SAFETIES and not rack_safeties and not spotter:
        setup = "training ALONE, no rack pins"
    elif rack_safeties:
        setup = "rack pins set"
    else:
        setup = "training alone"

    print(f"\n{'=' * 80}\n  {exercise.name} — {sessions} sessions — {setup}"
          f"\n  reps {exercise.rep_range[0]}-{exercise.rep_range[1]}   "
          f"jump {exercise.load_increment:.0f} lb\n{'=' * 80}")

    for n in range(1, sessions + 1):
        plan = prescribe(exercise, state, 3, gym, spotter, day)
        rirs = "/".join(str(p.target_rir) + ("*" if p.capped else "") for p in plan)
        print(f"\nSession {n:>2}   do: {plan[0].target_weight:.0f} lb x "
              f"{plan[0].target_reps}    target RIR by set: {rirs}")

        sets = []
        for p in plan:
            reps, rir = perform(p.target_weight, p.set_index, p.target_reps)
            sets.append(SetLog(
                set_index=p.set_index, weight=p.target_weight, reps=reps, rir=rir,
                target_weight=p.target_weight, target_reps=p.target_reps,
                target_rir=p.target_rir, stopped_at_cap=p.capped,
            ))
        print("           got: " + "   ".join(
            f"S{s.set_index} {s.reps}r @RIR{s.rir}" for s in sets))

        d = progress(exercise, state, sets, day)
        print(f"           -> {d.diagnosis.value.upper():<20} {d.message}")
        for note in d.notes:
            print(f"              · {note}")
        for opt in d.intervention_options:
            print(f"              option: {opt}")
        if d.intervention_options:
            print("              [nothing applied — waiting on your choice]")
            break

        state = apply(state, d, day)
        day += timedelta(days=4)          # push/pull/legs/rest rotation

    print("\n  * = RIR target raised by the safety floor")


LAT_PULLDOWN = make_exercise(
    "lat_pulldown", "Lat Pulldown", "cable",
    primary=["lats"], secondary=["biceps", "upper back"],
    substitutes=["Pull-Up"],
)


def calibration_perform(target_reps: int, true_weight: float, increment: float, attempted: float):
    """Same idea as make_lifter() above, but for the calibration ramp: a lifter
    with a real capacity ceiling at the target rep count, reporting the 5-way
    category a real person would pick rather than a precise RIR."""
    steps_off = round((true_weight - attempted) / increment)
    achievable = max(0, target_reps + steps_off * 2)
    if achievable >= target_reps + 6:
        rating = CalibrationRating.VERY_EASY
    elif achievable > target_reps:
        rating = CalibrationRating.SLIGHTLY_EASY
    elif achievable == target_reps:
        rating = CalibrationRating.HIT_AT_LIMIT
    elif achievable >= target_reps - 3:
        rating = CalibrationRating.SLIGHTLY_HARD
    else:
        rating = CalibrationRating.VERY_HARD
    actual_reps = min(achievable, target_reps)   # stops at the assigned number when it's easy
    return rating, actual_reps


def run_calibration(exercise: Exercise, first_guess_lb: float, true_weight_lb: float) -> None:
    target = calibration_target_reps(exercise)
    print(f"\n{'=' * 80}\n  CALIBRATION — {exercise.name} — first time, no history"
          f"\n  aiming for {target} reps (middle of {exercise.rep_range[0]}-{exercise.rep_range[1]})"
          f"  ·  jump {exercise.load_increment:.0f} lb\n{'=' * 80}")

    weight = first_guess_lb
    final = None
    for i in range(1, CALIBRATION_MAX_SETS + 1):
        rating, reps = calibration_perform(target, true_weight_lb, exercise.load_increment, weight)
        step = calibrate_step(exercise, weight, rating, reps)
        print(f"  Set {i}: attempt {weight:>3.0f} lb x {target}  ->  got {reps} reps, "
              f"rated {rating.value:<13}  ->  next: {step.next_weight:>3.0f} lb"
              + ("  [CONVERGED]" if step.converged else ""))
        final = SetLog(set_index=i, weight=weight, reps=reps,
                        target_weight=0, target_reps=0, target_rir=0)
        if step.converged:
            break
        weight = step.next_weight
    else:
        print(f"  Budget exhausted after {CALIBRATION_MAX_SETS} sets — using the last set as the baseline anyway.")

    state = bootstrap(exercise, final, date(2026, 8, 15))
    print(f"  -> Next session starts from: {state.current_weight:.0f} lb x {state.current_rep_target}")


if __name__ == "__main__":
    # Your actual push-day bench. No safety cap: a Smith bar racks anywhere.
    run(SMITH_BENCH, start_lb=135, ceiling_lb=185, sessions=14, rack_safeties=False)

    # Contrast: a free barbell, training alone, no pins. Watch the last set get capped.
    run(BARBELL_BENCH, start_lb=135, ceiling_lb=185, sessions=4, rack_safeties=False)

    # Calibration: a brand-new exercise, first guess too light — should climb and converge.
    run_calibration(LAT_PULLDOWN, first_guess_lb=40, true_weight_lb=65)

    # Calibration: first guess too heavy — should drop and converge.
    run_calibration(LAT_PULLDOWN, first_guess_lb=90, true_weight_lb=65)
