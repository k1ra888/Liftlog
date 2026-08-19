"""Engine tests — the scenarios listed in spec.md §7.

These are the cases that decide whether the engine is right. Read the test names:
they are the behaviour contract.
"""

from datetime import date, timedelta

import pytest

from engine import (
    CapReason,
    Diagnosis,
    Equipment,
    Exercise,
    ExerciseState,
    FailureRisk,
    GymProfile,
    Outcome,
    SetLog,
    apply,
    classify,
    prescribe,
    progress,
    rir_floor,
    rir_ramp,
    round_to_increment,
)

TODAY = date(2026, 8, 15)

BENCH = Exercise(
    id="barbell_bench_press",
    name="Barbell Bench Press",
    primary_muscles=("chest", "front delts"),
    secondary_muscles=("triceps",),
    rep_range=(5, 8),
    load_increment=2.5,
    equipment=Equipment.BARBELL,
    failure_risk=FailureRisk.NEEDS_SAFETIES,
    substitutes=("Dumbbell Press", "Machine Chest Press"),
)

PULLDOWN = Exercise(
    id="lat_pulldown",
    name="Lat Pulldown",
    primary_muscles=("lats",),
    secondary_muscles=("biceps", "upper back"),
    rep_range=(10, 15),
    load_increment=5.0,
    equipment=Equipment.MACHINE,
    failure_risk=FailureRisk.SAFE_TO_FAILURE,
)

PULLUP = Exercise(
    id="pullup",
    name="Pull-Up",
    primary_muscles=("lats",),
    secondary_muscles=("biceps",),
    rep_range=(5, 10),
    load_increment=2.5,
    equipment=Equipment.BODYWEIGHT,
    failure_risk=FailureRisk.SAFE_TO_FAILURE,
    is_bodyweight=True,
)

SOLO = GymProfile(has_rack_safeties=False)
RACK = GymProfile(has_rack_safeties=True)


def logged(plan, reps_per_set, rir_per_set=None):
    """Turn a prescription into logged sets with the given actual reps."""
    out = []
    for p, reps in zip(plan, reps_per_set):
        rir = None
        if rir_per_set is not None:
            rir = rir_per_set[plan.index(p)]
        out.append(
            SetLog(
                set_index=p.set_index,
                weight=p.target_weight,
                reps=reps,
                rir=rir,
                target_weight=p.target_weight,
                target_reps=p.target_reps,
                target_rir=p.target_rir,
                stopped_at_cap=p.capped,
            )
        )
    return out


# ------------------------------------------------------------------ primitives


def test_rir_ramp_moves_from_conservative_to_failure():
    assert rir_ramp(1) == [0]
    assert rir_ramp(2) == [1, 0]
    assert rir_ramp(3) == [2, 1, 0]
    assert rir_ramp(4) == [2, 1, 1, 0]


def test_round_to_increment_respects_available_plates():
    assert round_to_increment(101.2, 2.5) == 100.0
    assert round_to_increment(103.0, 2.5) == 102.5
    assert round_to_increment(99.0, 2.5, down=True) == 97.5


# ------------------------------------------------------------------ safety layer


def test_safe_exercise_never_capped_even_training_alone():
    floor, reason, _ = rir_floor(PULLDOWN, SOLO, spotter_present=False)
    assert floor == 0 and reason == CapReason.NONE


def test_barbell_bench_alone_without_safeties_is_capped():
    floor, reason, advice = rir_floor(BENCH, SOLO, spotter_present=False)
    assert floor == 1
    assert reason == CapReason.SOLO_NO_SAFETIES
    assert "rack pins" in advice
    assert "Dumbbell Press" in advice


def test_rack_safeties_remove_the_cap():
    floor, reason, _ = rir_floor(BENCH, RACK, spotter_present=False)
    assert floor == 0 and reason == CapReason.NONE


def test_spotter_removes_the_cap():
    floor, _, _ = rir_floor(BENCH, SOLO, spotter_present=True)
    assert floor == 0


def test_cap_only_binds_on_the_last_set():
    """Set 1's natural target is RIR 2, which already clears a floor of 1. Only the
    final set (natural RIR 0) actually gets clamped."""
    plan = prescribe(
        BENCH,
        ExerciseState("barbell_bench_press", 100.0, 5, last_performed_date=TODAY),
        num_sets=3, gym=SOLO, spotter_present=False, today=TODAY,
    )
    assert [p.target_rir for p in plan] == [2, 1, 1]
    assert [p.capped for p in plan] == [False, False, True]


# ------------------------------------------------------------------ classification


def test_set1_miss_vs_later_set_miss_are_different_outcomes():
    plan = prescribe(PULLDOWN, ExerciseState("lat_pulldown", 60.0, 10,
                     last_performed_date=TODAY), 3, RACK, False, TODAY)
    assert classify(logged(plan, [9, 10, 10])) == Outcome.MISS
    assert classify(logged(plan, [10, 10, 8])) == Outcome.PARTIAL
    assert classify(logged(plan, [10, 10, 10])) == Outcome.HIT


# ------------------------------------------------------------------ progression


def test_clean_hit_adds_a_rep():
    state = ExerciseState("lat_pulldown", 60.0, 10, last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [10, 10, 10], [2, 1, 1]), TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_REPS
    assert d.next_rep_target == 11
    assert d.next_weight == 60.0


def test_top_of_rep_range_adds_load_and_resets_reps():
    state = ExerciseState("lat_pulldown", 60.0, 15, last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [15, 15, 15], [2, 1, 1]), TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_LOAD
    assert d.next_weight == 65.0
    assert d.next_rep_target == 10


def test_high_rir_moves_by_reps_not_a_load_jump():
    """RIR 4+ is close to noise (Remmert et al.) — it must not trigger a big jump."""
    state = ExerciseState("lat_pulldown", 60.0, 10, last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [10, 10, 10], [5, 4, 4]), TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_REPS
    assert d.next_rep_target == 12
    assert d.next_weight == 60.0
    assert any("low-confidence" in n for n in d.notes)


def test_failure_on_set_one_holds_and_flags_a_mis_set_target():
    state = ExerciseState("lat_pulldown", 60.0, 10, last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [10, 10, 10], [0, 0, 0]), TODAY)
    assert d.diagnosis == Diagnosis.HOLD_CONSOLIDATE
    assert d.next_weight == 60.0
    assert any("set too aggressively" in n for n in d.notes)


def test_missing_rir_is_treated_as_neutral():
    state = ExerciseState("lat_pulldown", 60.0, 10, last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [10, 10, 10], None), TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_REPS
    assert d.next_rep_target == 11


# --------------------------------------------- the capped-RIR bug this must not have


def test_capped_rir1_progresses_but_true_rir1_also_progresses():
    """Both progress — the distinction that matters is against RIR 0."""
    state = ExerciseState("barbell_bench_press", 100.0, 5, last_performed_date=TODAY)
    plan = prescribe(BENCH, state, 3, SOLO, False, TODAY)
    d = progress(BENCH, state, logged(plan, [5, 5, 5], [2, 1, 1]), TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_REPS


def test_capped_set_one_is_not_read_as_true_failure():
    """The bug guard. If set 1 were somehow cap-limited and logged RIR 1, the engine
    must treat it as 'had more available', not as a true effort ceiling."""
    state = ExerciseState("barbell_bench_press", 100.0, 5, last_performed_date=TODAY)
    plan = prescribe(BENCH, state, 3, SOLO, False, TODAY)
    sets = logged(plan, [5, 5, 5], [1, 1, 1])
    sets[0].stopped_at_cap = True
    d = progress(BENCH, state, sets, TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_REPS
    assert any("ceiling, not a true effort reading" in n for n in d.notes)


# ------------------------------------------------------------------ fatigue vs load


def test_later_set_shortfall_is_diagnosed_as_fatigue_not_excess_load():
    """The distinction most apps get wrong: they cut the weight when the real cause
    was a short rest interval."""
    state = ExerciseState("lat_pulldown", 60.0, 12, last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [12, 11, 8], [2, 1, 0]), TODAY)
    assert d.diagnosis == Diagnosis.REPEAT_FATIGUE
    assert d.next_weight == 60.0
    assert d.consecutive_stalls == 0          # explicitly NOT a stall
    assert "fatigue, not" in d.message


def test_steep_dropoff_is_flagged_against_the_literature_band():
    state = ExerciseState("lat_pulldown", 60.0, 12, last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [12, 6, 4], [2, 1, 0]), TODAY)
    assert any("steeper than typical" in n for n in d.notes)


# ------------------------------------------------------------------ stalls


def test_three_consecutive_set1_misses_triggers_intervention_not_auto_deload():
    state = ExerciseState("lat_pulldown", 60.0, 12, consecutive_stalls=2,
                          last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [9, 9, 8], [0, 0, 0]), TODAY)
    assert d.diagnosis == Diagnosis.STALL_INTERVENTION
    assert d.consecutive_stalls == 3
    assert d.next_weight == 60.0              # nothing applied automatically
    assert len(d.intervention_options) >= 1


def test_a_hit_resets_the_stall_counter():
    state = ExerciseState("lat_pulldown", 60.0, 12, consecutive_stalls=2,
                          last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [12, 12, 12], [2, 1, 1]), TODAY)
    assert d.consecutive_stalls == 0


# ------------------------------------------------------------------ edge cases


def test_first_ever_session_prescribes_nothing():
    assert prescribe(BENCH, None, 3, RACK, False, TODAY) == []


def test_bootstrap_turns_a_first_log_into_real_state():
    """prescribe() returns [] with no state; bootstrap() is the other half of that
    contract — without it, a first-time log never becomes something prescribe() can
    build on next session."""
    from engine import bootstrap
    first = SetLog(set_index=1, weight=95.0, reps=6, target_weight=0, target_reps=0, target_rir=0)
    state = bootstrap(BENCH, first, TODAY)
    assert state.current_weight == 95.0
    assert state.current_rep_target == 6          # within BENCH's rep_range (5, 8)
    assert state.last_performed_date == TODAY
    assert state.consecutive_stalls == 0 and state.consecutive_fatigue == 0


def test_bootstrap_clamps_reps_into_the_rep_range():
    from engine import bootstrap
    too_many = SetLog(set_index=1, weight=95.0, reps=20, target_weight=0, target_reps=0, target_rir=0)
    too_few = SetLog(set_index=1, weight=95.0, reps=1, target_weight=0, target_reps=0, target_rir=0)
    assert bootstrap(BENCH, too_many, TODAY).current_rep_target == 8   # BENCH hi
    assert bootstrap(BENCH, too_few, TODAY).current_rep_target == 5    # BENCH lo


def test_layoff_over_two_weeks_reduces_the_prescribed_weight():
    stale = TODAY - timedelta(days=30)
    state = ExerciseState("barbell_bench_press", 100.0, 5, last_performed_date=stale)
    plan = prescribe(BENCH, state, 3, RACK, False, TODAY)
    assert plan[0].target_weight == 90.0


def test_short_gap_does_not_reduce_weight():
    recent = TODAY - timedelta(days=4)
    state = ExerciseState("barbell_bench_press", 100.0, 5, last_performed_date=recent)
    plan = prescribe(BENCH, state, 3, RACK, False, TODAY)
    assert plan[0].target_weight == 100.0


def test_bodyweight_lift_never_adds_load():
    state = ExerciseState("pullup", 0.0, 10, last_performed_date=TODAY)
    plan = prescribe(PULLUP, state, 3, RACK, False, TODAY)
    d = progress(PULLUP, state, logged(plan, [10, 10, 10], [2, 1, 1]), TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_REPS
    assert d.next_weight == 0.0
    assert d.next_rep_target == 11            # extends past the range top


def test_warmups_are_excluded_from_every_calculation():
    state = ExerciseState("lat_pulldown", 60.0, 10, last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    sets = logged(plan, [10, 10, 10], [2, 1, 1])
    sets.insert(0, SetLog(set_index=0, weight=20.0, reps=15, is_warmup=True))
    d = progress(PULLDOWN, state, sets, TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_REPS


# ------------------------------------------------------------------ integration


def test_eight_week_progression_is_monotonic_and_terminates():
    """Sanity: a lifter who hits every target should climb steadily, not oscillate."""
    state = ExerciseState("lat_pulldown", 60.0, 10, last_performed_date=TODAY)
    day = TODAY
    seen = []
    for _ in range(16):
        plan = prescribe(PULLDOWN, state, 3, RACK, False, day)
        reps = [p.target_reps for p in plan]
        d = progress(PULLDOWN, state, logged(plan, reps, [2, 1, 1]), day)
        state = apply(state, d, day)
        seen.append((state.current_weight, state.current_rep_target))
        day += timedelta(days=3)

    assert state.current_weight > 60.0
    # weight never decreases
    assert all(b[0] >= a[0] for a, b in zip(seen, seen[1:]))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


# ------------------------------------------------- regression: the fatigue deadlock


def test_persistent_fatigue_does_not_deadlock_the_lifter():
    """Caught by the simulation, not by the unit tests. A lifter whose set 1 keeps
    hitting while set 3 keeps fading was previously held at the same prescription
    forever — worse than the behaviour it replaced."""
    state = ExerciseState("lat_pulldown", 60.0, 12, last_performed_date=TODAY)
    start = (state.current_weight, state.current_rep_target)
    seen = []
    for _ in range(9):
        plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
        # set 1 always hits, set 3 always falls one short
        d = progress(PULLDOWN, state,
                     logged(plan, [plan[0].target_reps, plan[0].target_reps,
                                   plan[0].target_reps - 1], [1, 1, 0]), TODAY)
        state = apply(state, d, TODAY)
        seen.append(d.diagnosis)

    assert Diagnosis.REPEAT_FATIGUE in seen, "transient fatigue must still be tolerated"
    assert any(d in (Diagnosis.PROGRESS_REPS, Diagnosis.PROGRESS_LOAD) for d in seen), \
        "engine must eventually progress on set 1's merit rather than holding forever"
    assert (state.current_weight, state.current_rep_target) != start, \
        "prescription must actually advance over the window"
    # Known v1 limitation: this oscillates (progress every ~3rd session) because rep
    # targets are flat across sets. Fitted per-set decay in v1.1 removes the oscillation.


def test_a_clean_hit_clears_the_fatigue_counter():
    state = ExerciseState("lat_pulldown", 60.0, 12, consecutive_fatigue=2,
                          last_performed_date=TODAY)
    plan = prescribe(PULLDOWN, state, 3, RACK, False, TODAY)
    d = progress(PULLDOWN, state, logged(plan, [12, 12, 12], [2, 1, 1]), TODAY)
    assert d.consecutive_fatigue == 0


# ------------------------------------------------------------------ library


def test_custom_exercise_needs_only_name_muscles_and_equipment():
    """The add-your-own flow must not be an eight-field form."""
    from engine import make_exercise
    ex = make_exercise("pec_deck", "Pec Deck", "machine", primary=["chest"])
    assert ex.load_increment == 5.0
    assert ex.rep_range == (10, 15)
    assert ex.failure_risk.value == "safe_to_failure"


def test_every_derived_field_can_be_overridden():
    from engine import make_exercise
    ex = make_exercise("x", "X", "cable", primary=["triceps"],
                       increment=5.0, rep_range=(6, 8), rest_seconds=200)
    assert (ex.load_increment, ex.rep_range, ex.default_rest_seconds) == (5.0, (6, 8), 200)


def test_two_point_five_pound_plates_mean_five_pound_jumps_everywhere():
    """With 2.5 lb plates available, every preset standardizes on a 5 lb jump —
    not just dumbbells and cables, which were already 5 lb."""
    from engine import PRESETS
    for name, preset in PRESETS.items():
        assert preset["increment"] == 5.0, f"{name} increment should be 5.0"


def test_fixed_bars_get_a_wide_rep_range_to_absorb_coarse_jumps():
    from engine import PRESETS
    lo, hi = PRESETS["fixed_bar"]["rep_range"]
    assert hi - lo >= 6


def test_rotation_is_not_calendar_based():
    from engine import next_in_rotation
    assert next_in_rotation(None) == "push"
    assert next_in_rotation("push") == "pull"
    assert next_in_rotation("rest") == "push"


def test_fractional_volume_counts_secondaries_at_half():
    from engine import make_exercise, weekly_volume
    press = make_exercise("p", "Press", "smith",
                          primary=["chest"], secondary=["triceps"])
    v = weekly_volume([(press, 4)])
    assert v["chest"] == 4.0
    assert v["triceps"] == 2.0


# ------------------- regression: off-grid starting weights lost load every cycle


def test_load_progression_adds_the_full_increment_from_an_off_grid_weight():
    """At a 5 lb increment, 137.5 lb is off-grid (not a multiple of 5). Re-rounding
    142.5 onto an absolute 5 lb grid (banker's rounding) would silently give back
    2.5 lb instead of adding the full increment."""
    from engine import make_exercise
    smith = make_exercise("smith", "Smith Bench", "smith", primary=["chest"])
    state = ExerciseState("smith", 137.5, smith.rep_range[1], last_performed_date=TODAY)
    plan = prescribe(smith, state, 3, RACK, False, TODAY)
    top = plan[0].target_reps
    d = progress(smith, state, logged(plan, [top] * 3, [2, 1, 1]), TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_LOAD
    assert d.next_weight == 142.5, "must add the full 5 lb, not snap back to 140"


def test_layoff_deload_keeps_an_off_grid_weight_loadable():
    from engine import make_exercise
    smith = make_exercise("smith", "Smith Bench", "smith", primary=["chest"])
    stale = TODAY - timedelta(days=30)
    state = ExerciseState("smith", 137.5, 6, last_performed_date=stale)
    plan = prescribe(smith, state, 3, RACK, False, TODAY)
    # 10% of 137.5 is 13.75 -> floors to one 5 lb step down: 137.5 - 10 = 127.5
    assert plan[0].target_weight == 127.5


# ------------------------------------------- exercise catalog (pull/legs/core)


def test_exercise_library_has_no_duplicate_ids():
    """PUSH_DAY plus the new pull/leg/core entries share one id namespace."""
    from engine import EXERCISE_LIBRARY
    ids = [ex.id for ex in EXERCISE_LIBRARY]
    assert len(ids) == len(set(ids))


def test_exercise_library_covers_every_major_muscle_group():
    """The catalog exists so pull/leg day can be picked against real fractional
    volume numbers — it is useless for that if a muscle group has no entries."""
    from engine import EXERCISE_LIBRARY
    covered = set()
    for ex in EXERCISE_LIBRARY:
        covered.update(ex.primary_muscles)
        covered.update(ex.secondary_muscles)
    expected = {
        "chest", "front delts", "side delts", "triceps",         # push
        "lats", "upper back", "biceps", "traps",                 # pull
        "quads", "hamstrings", "glutes", "calves",                # legs
        "abs",                                                    # core
    }
    missing = expected - covered
    assert not missing, f"no exercise trains: {missing}"


def test_pull_day_and_leg_day_are_drawn_from_the_catalog():
    """PULL_DAY/LEG_DAY must be the same objects as their catalog entries, not
    re-defined copies that could drift out of sync with EXERCISE_LIBRARY."""
    from engine import EXERCISE_BY_ID, LEG_DAY, PULL_DAY
    assert all(ex is EXERCISE_BY_ID[ex.id] for ex in PULL_DAY)
    assert all(ex is EXERCISE_BY_ID[ex.id] for ex in LEG_DAY)
    assert len(PULL_DAY) == 4 and len(LEG_DAY) == 4


def test_weekly_volume_runs_over_the_full_catalog():
    """Smoke test: every entry must be shaped correctly for fractional counting,
    not just the ones already covered by other tests."""
    from engine import EXERCISE_LIBRARY, weekly_volume
    v = weekly_volume([(ex, 3) for ex in EXERCISE_LIBRARY])
    assert v["quads"] > 0 and v["lats"] > 0 and v["chest"] > 0


# ------------------------------------------------------------ "the numbers"


def test_rotation_volume_sums_across_push_pull_legs():
    from engine import make_exercise, rotation_volume
    chest_ex = make_exercise("c", "C", "smith", primary=["chest"])
    back_ex = make_exercise("b", "B", "cable", primary=["upper back"], secondary=["chest"])
    v = rotation_volume({
        "push": [(chest_ex, 3)],
        "pull": [(back_ex, 2)],
    })
    # chest: 3.0 direct on push + 1.0 indirect (0.5 * 2) on pull
    assert v["chest"] == 4.0
    assert v["upper back"] == 2.0


def test_rotation_volume_rejects_a_day_not_in_the_rotation():
    from engine import make_exercise, rotation_volume
    ex = make_exercise("c", "C", "smith", primary=["chest"])
    with pytest.raises(ValueError):
        rotation_volume({"cardio": [(ex, 3)]})


def test_rest_day_contributes_nothing_because_it_has_no_exercises():
    """Confirms the rotation's 4th day is a no-op for volume, not a missing case."""
    from engine import rotation_volume
    assert rotation_volume({"rest": []}) == {}


def test_routine_preview_matches_a_manual_rotation_volume_call():
    from engine import LEG_DAY, PULL_DAY, PUSH_DAY_SESSION, rotation_volume, routine_preview
    expected = rotation_volume({
        "push": [(ex, 3) for ex in PUSH_DAY_SESSION],
        "pull": [(ex, 3) for ex in PULL_DAY],
        "legs": [(ex, 3) for ex in LEG_DAY],
    })
    assert routine_preview() == expected


def test_routine_preview_does_not_double_count_pushs_alternating_variants():
    """The bug this must not have: PUSH_DAY lists both Smith and dumbbell variants
    of bench/incline, which are never trained in the same session."""
    from engine import routine_preview
    v = routine_preview()
    assert v["chest"] == 6.0
    assert v["front delts"] == 9.0


def test_low_confidence_note_is_absent_when_load_is_added():
    """The note said 'moving by reps' on lines that added weight."""
    from engine import make_exercise
    smith = make_exercise("smith", "Smith Bench", "smith", primary=["chest"])
    state = ExerciseState("smith", 135.0, smith.rep_range[1], last_performed_date=TODAY)
    plan = prescribe(smith, state, 3, RACK, False, TODAY)
    top = plan[0].target_reps
    d = progress(smith, state, logged(plan, [top] * 3, [4, 4, 4]), TODAY)
    assert d.diagnosis == Diagnosis.PROGRESS_LOAD
    assert not any("moving by reps" in n for n in d.notes)
