"""Generates parity/fixtures.js from the real Python engine.

Run: ./.venv/Scripts/python.exe tools/gen_parity_fixtures.py

Each fixture is {name, fn, args, expected, kind[, notes_min]}. `fn` names a
function the JS harness resolves against Engine/Library. `kind` tells the harness
how to compare — see parity/harness.html's COMPARATORS. Deliberately NOT
compared: free-text message/notes/advice strings (presentation, not logic — see
js/engine.js's file header for the reasoning). `expected` therefore already has
those fields stripped where relevant.

This script does not touch engine/ or tests/ — it only reads them. Re-run it
whenever engine/ changes; parity/fixtures.js is generated output, not hand-edited.
"""

import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import (
    CalibrationRating,
    Equipment, Exercise, ExerciseState, FailureRisk, GymProfile, SetLog,
    apply, bootstrap, calibrate_step, calibration_target_reps, classify,
    prescribe, progress, rir_floor, rir_ramp, round_to_increment,
)
from engine.library import rotation_volume, routine_preview, weekly_volume, next_in_rotation


class _Encoder(json.JSONEncoder):
    """Handles dataclasses (recursively, including nested lists/dicts of them),
    Enum members (-> .value), and date objects (-> isoformat) wherever json.dumps
    encounters them, at any depth."""

    def default(self, o):
        if is_dataclass(o) and not isinstance(o, type):
            return asdict(o)
        if isinstance(o, Enum):
            return o.value
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)


def j(obj):
    return json.loads(json.dumps(obj, cls=_Encoder))


TODAY = date(2026, 8, 15)

BENCH = Exercise(
    id="barbell_bench_press", name="Barbell Bench Press",
    primary_muscles=("chest", "front delts"), secondary_muscles=("triceps",),
    rep_range=(5, 8), load_increment=2.5, equipment=Equipment.BARBELL,
    failure_risk=FailureRisk.NEEDS_SAFETIES,
    substitutes=("Dumbbell Press", "Machine Chest Press"),
)
PULLDOWN = Exercise(
    id="lat_pulldown", name="Lat Pulldown", primary_muscles=("lats",),
    secondary_muscles=("biceps", "upper back"), rep_range=(10, 15),
    load_increment=5.0, equipment=Equipment.MACHINE,
    failure_risk=FailureRisk.SAFE_TO_FAILURE,
)
SMITH = Exercise(
    id="smith", name="Smith Bench", primary_muscles=("chest",),
    rep_range=(6, 10), load_increment=10.0, equipment=Equipment.BARBELL,
    failure_risk=FailureRisk.BAILOUT_POSSIBLE,
)
PULLUP = Exercise(
    id="pullup", name="Pull-Up", primary_muscles=("lats",),
    secondary_muscles=("biceps",), rep_range=(5, 10), load_increment=2.5,
    equipment=Equipment.BODYWEIGHT, failure_risk=FailureRisk.SAFE_TO_FAILURE,
    is_bodyweight=True,
)

SOLO = GymProfile(has_rack_safeties=False)
RACK = GymProfile(has_rack_safeties=True)


def logged(plan, reps_per_set, rir_per_set=None):
    """plan: list of SetPrescription. Mirrors tests/test_engine.py's helper."""
    out = []
    for i, (p, reps) in enumerate(zip(plan, reps_per_set)):
        rir = rir_per_set[i] if rir_per_set is not None else None
        out.append(SetLog(
            set_index=p.set_index, weight=p.target_weight, reps=reps, rir=rir,
            target_weight=p.target_weight, target_reps=p.target_reps,
            target_rir=p.target_rir, stopped_at_cap=p.capped,
        ))
    return out


fixtures = []


def add(name, fn, args, expected, kind, **extra):
    fx = {"name": name, "fn": fn, "args": args, "expected": expected, "kind": kind}
    fx.update(extra)
    fixtures.append(fx)


# ---------------------------------------------------------------- primitives

for w, inc, down in [(101.2, 2.5, False), (103.0, 2.5, False), (99.0, 2.5, True),
                      (105.0, 10.0, False), (135.0, 10.0, False)]:
    add(f"round_to_increment({w}, {inc}, down={down})", "roundToIncrement",
        [w, inc, down], round_to_increment(w, inc, down=down), "scalar")

for n in [1, 2, 3, 4]:
    add(f"rir_ramp({n})", "rirRamp", [n], rir_ramp(n), "scalar")

for last in [None, "push", "rest"]:
    add(f"next_in_rotation({last!r})", "nextInRotation", [last], next_in_rotation(last), "scalar")

# ---------------------------------------------------------------- safety layer

for name, ex, gym, spotter in [
    ("floor: safe exercise never capped", PULLDOWN, SOLO, False),
    ("floor: barbell alone, no safeties", BENCH, SOLO, False),
    ("floor: rack safeties remove cap", BENCH, RACK, False),
    ("floor: spotter removes cap", BENCH, SOLO, True),
]:
    floor, reason, _advice = rir_floor(ex, gym, spotter)
    add(name, "rirFloor", [j(ex), j(gym), spotter], [floor, reason.value], "rirFloor")

_cap_state = ExerciseState("barbell_bench_press", 100.0, 5, last_performed_date=TODAY)
_cap_plan = prescribe(BENCH, _cap_state, 3, SOLO, False, TODAY)
add(
    "prescribe: cap only binds on last set", "prescribe",
    [j(BENCH), j(_cap_state), 3, j(SOLO), False, TODAY.isoformat()],
    j(_cap_plan), "prescriptions",
)

# ---------------------------------------------------------------- classification

_pd_state = ExerciseState("lat_pulldown", 60.0, 10, last_performed_date=TODAY)
_pd_plan = prescribe(PULLDOWN, _pd_state, 3, RACK, False, TODAY)
add("classify: set1 miss", "classify", [j(logged(_pd_plan, [9, 10, 10]))], "miss", "scalar")
add("classify: later-set miss = partial", "classify", [j(logged(_pd_plan, [10, 10, 8]))], "partial", "scalar")
add("classify: clean hit", "classify", [j(logged(_pd_plan, [10, 10, 10]))], "hit", "scalar")

# ---------------------------------------------------------------- progression

def decision_expected(d):
    return {
        "diagnosis": d.diagnosis.value,
        "next_weight": d.next_weight,
        "next_rep_target": d.next_rep_target,
        "consecutive_stalls": d.consecutive_stalls,
        "consecutive_fatigue": d.consecutive_fatigue,
    }


def add_progress(name, ex, state, plan, reps, rirs, **extra):
    sets = logged(plan, reps, rirs)
    d = progress(ex, state, sets, TODAY)
    add(
        name, "progress",
        [j(ex), j(state), j(sets), TODAY.isoformat()],
        decision_expected(d), "decision", **extra,
    )
    return d


_state = ExerciseState("lat_pulldown", 60.0, 10, last_performed_date=TODAY)
_plan = prescribe(PULLDOWN, _state, 3, RACK, False, TODAY)
add_progress("progress: clean hit adds a rep", PULLDOWN, _state, _plan, [10, 10, 10], [2, 1, 1])

_state2 = ExerciseState("lat_pulldown", 60.0, 15, last_performed_date=TODAY)
_plan2 = prescribe(PULLDOWN, _state2, 3, RACK, False, TODAY)
add_progress("progress: top of range adds load, resets reps", PULLDOWN, _state2, _plan2, [15, 15, 15], [2, 1, 1])

add_progress("progress: high RIR moves by reps not load", PULLDOWN, _state, _plan, [10, 10, 10], [5, 4, 4])
add_progress("progress: failure on set1 holds", PULLDOWN, _state, _plan, [10, 10, 10], [0, 0, 0])
add_progress("progress: missing RIR treated as neutral", PULLDOWN, _state, _plan, [10, 10, 10], None)

_bench_state = ExerciseState("barbell_bench_press", 100.0, 5, last_performed_date=TODAY)
_bench_plan = prescribe(BENCH, _bench_state, 3, SOLO, False, TODAY)
add_progress("progress: capped RIR1 on set1 progresses", BENCH, _bench_state, _bench_plan, [5, 5, 5], [2, 1, 1])

_capped_sets = logged(_bench_plan, [5, 5, 5], [1, 1, 1])
_capped_sets[0].stopped_at_cap = True
_d_capped = progress(BENCH, _bench_state, _capped_sets, TODAY)
add(
    "progress: capped set1 not misread as true failure (bug guard)", "progress",
    [j(BENCH), j(_bench_state), j(_capped_sets), TODAY.isoformat()],
    decision_expected(_d_capped), "decision",
)

_fatigue_state = ExerciseState("lat_pulldown", 60.0, 12, last_performed_date=TODAY)
_fatigue_plan = prescribe(PULLDOWN, _fatigue_state, 3, RACK, False, TODAY)
add_progress("progress: later-set shortfall = fatigue not overload", PULLDOWN, _fatigue_state, _fatigue_plan, [12, 11, 8], [2, 1, 0])
add_progress("progress: steep dropoff flagged (note count)", PULLDOWN, _fatigue_state, _fatigue_plan, [12, 6, 4], [2, 1, 0], notes_min=1)

_fatigue_boundary_state = ExerciseState("lat_pulldown", 60.0, 12, consecutive_fatigue=2, last_performed_date=TODAY)
add_progress("progress: fatigue patience boundary falls through", PULLDOWN, _fatigue_boundary_state, _fatigue_plan, [12, 11, 8], [2, 1, 0])

_stall_state = ExerciseState("lat_pulldown", 60.0, 12, consecutive_stalls=2, last_performed_date=TODAY)
_stall_plan = prescribe(PULLDOWN, _stall_state, 3, RACK, False, TODAY)
add_progress("progress: 3rd consecutive miss triggers stall intervention", PULLDOWN, _stall_state, _stall_plan, [9, 9, 8], [0, 0, 0])
add_progress("progress: a hit resets the stall counter", PULLDOWN, _stall_state, _stall_plan, [12, 12, 12], [2, 1, 1])

_smith_state = ExerciseState("smith", 135.0, 10, last_performed_date=TODAY)
_smith_plan = prescribe(SMITH, _smith_state, 3, RACK, False, TODAY)
add_progress("progress: off-grid load adds full increment (bug guard)", SMITH, _smith_state, _smith_plan, [10, 10, 10], [2, 1, 1])

_bw_state = ExerciseState("pullup", 0.0, 10, last_performed_date=TODAY)
_bw_plan = prescribe(PULLUP, _bw_state, 3, RACK, False, TODAY)
add_progress("progress: bodyweight never adds load", PULLUP, _bw_state, _bw_plan, [10, 10, 10], [2, 1, 1])

# ---------------------------------------------------------------- prescribe: layoff

_stale_state = ExerciseState("barbell_bench_press", 100.0, 5, last_performed_date=TODAY - timedelta(days=30))
add(
    "prescribe: layoff >14d reduces weight", "prescribe",
    [j(BENCH), j(_stale_state), 3, j(RACK), False, TODAY.isoformat()],
    90.0, "firstPrescriptionWeight",
)
_recent_state = ExerciseState("barbell_bench_press", 100.0, 5, last_performed_date=TODAY - timedelta(days=4))
add(
    "prescribe: short gap does not reduce weight", "prescribe",
    [j(BENCH), j(_recent_state), 3, j(RACK), False, TODAY.isoformat()],
    100.0, "firstPrescriptionWeight",
)
_offgrid_stale = ExerciseState("smith", 135.0, 6, last_performed_date=TODAY - timedelta(days=30))
add(
    "prescribe: layoff deload keeps off-grid weight loadable", "prescribe",
    [j(SMITH), j(_offgrid_stale), 3, j(RACK), False, TODAY.isoformat()],
    125.0, "firstPrescriptionWeight",
)

# ---------------------------------------------------------------- apply / bootstrap

_apply_state = ExerciseState("lat_pulldown", 60.0, 10, last_performed_date=TODAY)
_apply_decision = progress(PULLDOWN, _apply_state, logged(_plan, [10, 10, 10], [2, 1, 1]), TODAY)
_applied = apply(_apply_state, _apply_decision, TODAY)
add(
    "apply: folds decision into state", "apply",
    [j(_apply_state), j(_apply_decision), TODAY.isoformat()],
    j(_applied), "state",
)

_first_log = SetLog(set_index=1, weight=95.0, reps=6, target_weight=0, target_reps=0, target_rir=0)
add("bootstrap: first log becomes state", "bootstrap", [j(BENCH), j(_first_log), TODAY.isoformat()],
    j(bootstrap(BENCH, _first_log, TODAY)), "state")

_too_many = SetLog(set_index=1, weight=95.0, reps=20, target_weight=0, target_reps=0, target_rir=0)
add("bootstrap: clamps reps to range top", "bootstrap", [j(BENCH), j(_too_many), TODAY.isoformat()],
    j(bootstrap(BENCH, _too_many, TODAY)), "state")

_too_few = SetLog(set_index=1, weight=95.0, reps=1, target_weight=0, target_reps=0, target_rir=0)
add("bootstrap: clamps reps to range floor", "bootstrap", [j(BENCH), j(_too_few), TODAY.isoformat()],
    j(bootstrap(BENCH, _too_few, TODAY)), "state")

# ---------------------------------------------------------------- calibration

for n, expected in [(PULLDOWN, calibration_target_reps(PULLDOWN)), (BENCH, calibration_target_reps(BENCH))]:
    add(f"calibration_target_reps({n.id})", "calibrationTargetReps", [j(n)], expected, "scalar")

for name, ex, weight, rating, reps in [
    ("calibrate: very easy adds 2 increments", PULLDOWN, 60.0, CalibrationRating.VERY_EASY, 18),
    ("calibrate: slightly easy adds 1 increment", PULLDOWN, 60.0, CalibrationRating.SLIGHTLY_EASY, 13),
    ("calibrate: hit at limit converges", PULLDOWN, 60.0, CalibrationRating.HIT_AT_LIMIT, 12),
    ("calibrate: small miss drops 1 increment", PULLDOWN, 60.0, CalibrationRating.SLIGHTLY_HARD, 10),
    ("calibrate: big miss capped at 3 increments", PULLDOWN, 60.0, CalibrationRating.VERY_HARD, 2),
    ("calibrate: weighted floors at 1 increment", PULLDOWN, 10.0, CalibrationRating.VERY_HARD, 0),
    ("calibrate: bodyweight floors at 0", PULLUP, 0.0, CalibrationRating.VERY_HARD, 0),
]:
    step = calibrate_step(ex, weight, rating, reps)
    add(name, "calibrateStep", [j(ex), weight, rating.value, reps],
        {"next_weight": step.next_weight, "converged": step.converged}, "state")

# ---------------------------------------------------------------- volume

_press = Exercise(id="p", name="Press", primary_muscles=("chest",), secondary_muscles=("triceps",),
                   equipment=Equipment.BARBELL, load_increment=10.0)
add("weekly_volume: secondaries at half", "weeklyVolume", [[[j(_press), 4]]],
    weekly_volume([(_press, 4)]), "volume")

add(
    "rotation_volume: sums across days", "rotationVolume",
    [{"push": [[j(_press), 3]], "pull": [[j(PULLDOWN), 2]]}],
    rotation_volume({"push": [(_press, 3)], "pull": [(PULLDOWN, 2)]}), "volume",
)
add("rotation_volume: rejects unknown day", "rotationVolume", [{"cardio": [[j(_press), 3]]}], None, "throws")

add("routine_preview: full rotation, default 3 sets", "routinePreview", [3],
    routine_preview(3), "volume")

# ---------------------------------------------------------------- write output

out_path = Path(__file__).resolve().parent.parent / "parity" / "fixtures.js"
out_path.parent.mkdir(exist_ok=True)
out_path.write_text(
    "// GENERATED by tools/gen_parity_fixtures.py — do not hand-edit.\n"
    "const FIXTURES = " + json.dumps(fixtures, indent=2) + ";\n",
    encoding="utf-8",
)
print(f"wrote {len(fixtures)} fixtures to {out_path}")
