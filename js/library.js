/*
 * Exercise library — JS port of engine/library.py. Mirrors it 1:1: same ids, same
 * presets, same routines. Depends on Engine (js/engine.js) for the exercise()
 * factory and enums — load engine.js first.
 */

(function (global) {
  "use strict";

  const { Equipment, FailureRisk, exercise } = global.Engine;

  // Gym-specific presets. `increment` is the smallest jump ACTUALLY achievable —
  // not the smallest plate. A 5 lb plate loads a barbell in 10 lb steps because
  // you put one on each side.
  const PRESETS = {
    smith: {
      equipment: Equipment.BARBELL,
      increment: 10.0,
      failure_risk: FailureRisk.BAILOUT_POSSIBLE,
      rest: 150,
      rep_range: [6, 10],
    },
    barbell: {
      equipment: Equipment.BARBELL,
      increment: 10.0,
      failure_risk: FailureRisk.NEEDS_SAFETIES,
      rest: 150,
      rep_range: [6, 10],
    },
    dumbbell: {
      equipment: Equipment.DUMBBELL,
      increment: 5.0,
      failure_risk: FailureRisk.BAILOUT_POSSIBLE,
      rest: 120,
      rep_range: [8, 12],
    },
    fixed_bar: {
      equipment: Equipment.BARBELL,
      increment: 10.0,
      failure_risk: FailureRisk.BAILOUT_POSSIBLE,
      rest: 120,
      rep_range: [8, 15],
    },
    cable: {
      equipment: Equipment.CABLE,
      increment: 5.0,           // confirmed at the gym across all cable machines
      failure_risk: FailureRisk.SAFE_TO_FAILURE,
      rest: 90,
      rep_range: [10, 15],
    },
    machine: {
      equipment: Equipment.MACHINE,
      increment: 10.0,
      failure_risk: FailureRisk.SAFE_TO_FAILURE,
      rest: 90,
      rep_range: [10, 15],
    },
    bodyweight: {
      equipment: Equipment.BODYWEIGHT,
      increment: 2.5,
      failure_risk: FailureRisk.SAFE_TO_FAILURE,
      rest: 120,
      rep_range: [5, 12],
    },
  };

  function makeExercise(id, name, preset, primary, secondary = [], opts = {}) {
    const p = PRESETS[preset];
    if (!p) {
      throw new Error(`unknown preset ${JSON.stringify(preset)}; options: ${Object.keys(PRESETS).sort().join(", ")}`);
    }
    return exercise({
      id,
      name,
      primary_muscles: primary.slice(),
      secondary_muscles: secondary.slice(),
      rep_range: opts.rep_range || p.rep_range,
      load_increment: opts.increment !== undefined ? opts.increment : p.increment,
      equipment: p.equipment,
      failure_risk: opts.failure_risk || p.failure_risk,
      substitutes: (opts.substitutes || []).slice(),
      default_rest_seconds: opts.rest_seconds || p.rest,
      is_bodyweight: p.equipment === Equipment.BODYWEIGHT,
    });
  }

  // --------------------------------------------------------------- seeded routine
  // Push day, as actually trained.

  const PUSH_DAY = [
    makeExercise("smith_bench", "Smith Machine Bench", "smith",
      ["chest", "front delts"], ["triceps"],
      { substitutes: ["Dumbbell Bench"] }),
    makeExercise("db_bench", "Dumbbell Bench", "dumbbell",
      ["chest", "front delts"], ["triceps"],
      { substitutes: ["Smith Machine Bench"] }),
    makeExercise("smith_incline", "Smith Machine Incline", "smith",
      ["chest", "front delts"], ["triceps"],
      { substitutes: ["Dumbbell Incline"] }),
    makeExercise("db_incline", "Dumbbell Incline", "dumbbell",
      ["chest", "front delts"], ["triceps"],
      { substitutes: ["Smith Machine Incline"] }),
    makeExercise("standing_ohp_bar", "Standing Shoulder Press (fixed bar)", "fixed_bar",
      ["front delts"], ["triceps", "side delts"]),
    makeExercise("cable_oh_tricep", "Overhead Tricep Extension (rope)", "cable",
      ["triceps"]),
    makeExercise("cable_pushdown_bar", "Tricep Pushdown (bar)", "cable",
      ["triceps"]),
  ];

  // --------------------------------------------------------------- full catalog
  // A pick-from-this list, not a prescribed routine.

  const PUSH_EXTRA = [
    makeExercise("barbell_bench", "Barbell Bench Press", "barbell",
      ["chest", "front delts"], ["triceps"],
      { substitutes: ["Dumbbell Bench", "Smith Machine Bench"] }),
    makeExercise("pec_deck_fly", "Pec Deck / Chest Fly (machine)", "machine",
      ["chest"], [], { substitutes: ["Cable Chest Fly"] }),
    makeExercise("cable_fly", "Cable Chest Fly", "cable",
      ["chest"], [], { substitutes: ["Pec Deck / Chest Fly (machine)"] }),
    makeExercise("barbell_ohp", "Barbell Overhead Press", "barbell",
      ["front delts"], ["triceps", "side delts"],
      { failure_risk: FailureRisk.BAILOUT_POSSIBLE,
        substitutes: ["Standing Shoulder Press (fixed bar)", "Seated Dumbbell Shoulder Press"] }),
    makeExercise("db_shoulder_press", "Seated Dumbbell Shoulder Press", "dumbbell",
      ["front delts"], ["triceps", "side delts"],
      { substitutes: ["Standing Shoulder Press (fixed bar)"] }),
    makeExercise("machine_shoulder_press", "Machine Shoulder Press", "machine",
      ["front delts"], ["triceps", "side delts"]),
    makeExercise("db_lateral_raise", "Dumbbell Lateral Raise", "dumbbell",
      ["side delts"], [], { substitutes: ["Cable Lateral Raise"] }),
    makeExercise("cable_lateral_raise", "Cable Lateral Raise", "cable",
      ["side delts"], [], { substitutes: ["Dumbbell Lateral Raise"] }),
    makeExercise("ezbar_skull_crusher", "EZ-Bar Skull Crusher", "fixed_bar",
      ["triceps"]),
  ];

  const PUSH_EXERCISES = PUSH_DAY.concat(PUSH_EXTRA);

  const PULL_EXERCISES = [
    makeExercise("lat_pulldown", "Lat Pulldown", "cable",
      ["lats"], ["biceps", "upper back"], { substitutes: ["Pull-Up"] }),
    makeExercise("pullup", "Pull-Up", "bodyweight",
      ["lats"], ["biceps"], { substitutes: ["Lat Pulldown"] }),
    makeExercise("seated_cable_row", "Seated Cable Row", "cable",
      ["upper back"], ["lats", "biceps"],
      { substitutes: ["Chest-Supported Row", "Single-Arm Seated Cable Row"] }),
    makeExercise("single_arm_seated_row", "Single-Arm Seated Cable Row", "cable",
      ["upper back"], ["lats", "biceps"], { substitutes: ["Seated Cable Row"] }),
    makeExercise("chest_supported_row", "Chest-Supported Row (machine)", "machine",
      ["upper back"], ["lats", "biceps"], { substitutes: ["Seated Cable Row"] }),
    makeExercise("smith_row", "Smith Machine Bent-Over Row", "smith",
      ["upper back"], ["lats", "biceps"]),
    makeExercise("face_pull", "Face Pull (cable)", "cable",
      ["side delts"], ["upper back"]),
    makeExercise("reverse_pec_deck", "Reverse Pec Deck", "machine",
      ["side delts"], ["upper back"], { substitutes: ["Face Pull (cable)"] }),
    makeExercise("db_curl", "Dumbbell Bicep Curl", "dumbbell",
      ["biceps"]),
    makeExercise("cable_curl", "Cable Bicep Curl", "cable",
      ["biceps"], [], { substitutes: ["Dumbbell Bicep Curl"] }),
    makeExercise("preacher_curl_machine", "Preacher Curl (machine)", "machine",
      ["biceps"]),
    makeExercise("db_shrug", "Dumbbell Shrug", "dumbbell",
      ["traps"], ["upper back"]),
  ];

  const LEG_EXERCISES = [
    makeExercise("leg_press", "Leg Press (machine)", "machine",
      ["quads"], ["glutes"], { substitutes: ["Hack Squat", "Smith Machine Squat"] }),
    makeExercise("hack_squat", "Hack Squat (machine)", "machine",
      ["quads"], ["glutes"], { substitutes: ["Leg Press (machine)"] }),
    makeExercise("smith_squat", "Smith Machine Squat", "smith",
      ["quads"], ["glutes"], { substitutes: ["Leg Press (machine)"] }),
    makeExercise("leg_extension", "Leg Extension (machine)", "machine",
      ["quads"]),
    makeExercise("leg_curl_machine", "Leg Curl (machine)", "machine",
      ["hamstrings"]),
    makeExercise("db_rdl", "Dumbbell Romanian Deadlift", "dumbbell",
      ["hamstrings"], ["glutes"]),
    makeExercise("hip_thrust_machine", "Hip Thrust (machine)", "machine",
      ["glutes"], ["hamstrings"]),
    makeExercise("walking_lunge_db", "Dumbbell Walking Lunge", "dumbbell",
      ["quads"], ["glutes"]),
    makeExercise("standing_calf_raise", "Standing Calf Raise (machine)", "machine",
      ["calves"], [], { substitutes: ["Calf Raise (hack squat machine)", "Seated Calf Raise (machine)"] }),
    makeExercise("seated_calf_raise", "Seated Calf Raise (machine)", "machine",
      ["calves"], [], { substitutes: ["Calf Raise (hack squat machine)", "Standing Calf Raise (machine)"] }),
    makeExercise("calf_raise_hack_squat", "Calf Raise (hack squat machine)", "machine",
      ["calves"], [], { substitutes: ["Standing Calf Raise (machine)", "Seated Calf Raise (machine)"] }),
  ];

  const CORE_EXERCISES = [
    makeExercise("cable_crunch", "Cable Crunch", "cable", ["abs"]),
    makeExercise("hanging_leg_raise", "Hanging Leg Raise", "bodyweight", ["abs"]),
  ];

  const EXERCISE_LIBRARY = PUSH_EXERCISES.concat(PULL_EXERCISES, LEG_EXERCISES, CORE_EXERCISES);
  const EXERCISE_BY_ID = {};
  for (const ex of EXERCISE_LIBRARY) EXERCISE_BY_ID[ex.id] = ex;

  // --------------------------------------------------------------- pull / legs, as described

  const PULL_DAY = [
    EXERCISE_BY_ID["lat_pulldown"],
    EXERCISE_BY_ID["seated_cable_row"],
    EXERCISE_BY_ID["single_arm_seated_row"],
    EXERCISE_BY_ID["preacher_curl_machine"],
  ];

  const LEG_DAY = [
    EXERCISE_BY_ID["hack_squat"],
    EXERCISE_BY_ID["leg_extension"],
    EXERCISE_BY_ID["leg_curl_machine"],
    EXERCISE_BY_ID["calf_raise_hack_squat"],
  ];

  // PUSH_DAY lists BOTH equipment alternates for bench and incline; a real session
  // only ever does one of each pair. See library.py's comment — this bug bit the
  // Python "routine_preview()" once already, don't reintroduce it here.
  const PUSH_DAY_SESSION = [
    EXERCISE_BY_ID["smith_bench"],
    EXERCISE_BY_ID["smith_incline"],
    EXERCISE_BY_ID["standing_ohp_bar"],
    EXERCISE_BY_ID["cable_oh_tricep"],
    EXERCISE_BY_ID["cable_pushdown_bar"],
  ];

  const ROTATION = ["push", "pull", "legs", "rest"];

  function nextInRotation(last) {
    if (last === null || last === undefined || !ROTATION.includes(last)) {
      return ROTATION[0];
    }
    return ROTATION[(ROTATION.indexOf(last) + 1) % ROTATION.length];
  }

  function weeklyVolume(logged) {
    const out = {};
    for (const [ex, n] of logged) {
      for (const m of ex.primary_muscles) out[m] = (out[m] || 0) + 1.0 * n;
      for (const m of ex.secondary_muscles) out[m] = (out[m] || 0) + 0.5 * n;
    }
    return Object.fromEntries(
      Object.entries(out).sort((a, b) => b[1] - a[1])
    );
  }

  function rotationVolume(loggedByDay) {
    const combined = [];
    for (const day of Object.keys(loggedByDay)) {
      if (!ROTATION.includes(day)) {
        throw new Error(`unknown rotation day ${JSON.stringify(day)}; options: ${ROTATION.join(", ")}`);
      }
      combined.push(...loggedByDay[day]);
    }
    return weeklyVolume(combined);
  }

  function routinePreview(setsPerExercise = 3) {
    return rotationVolume({
      push: PUSH_DAY_SESSION.map((ex) => [ex, setsPerExercise]),
      pull: PULL_DAY.map((ex) => [ex, setsPerExercise]),
      legs: LEG_DAY.map((ex) => [ex, setsPerExercise]),
    });
  }

  global.Library = {
    PRESETS, makeExercise,
    PUSH_DAY, PUSH_EXTRA, PUSH_EXERCISES, PULL_EXERCISES, LEG_EXERCISES, CORE_EXERCISES,
    EXERCISE_LIBRARY, EXERCISE_BY_ID, PULL_DAY, LEG_DAY, PUSH_DAY_SESSION,
    ROTATION, nextInRotation, weeklyVolume, rotationVolume, routinePreview,
  };
})(typeof window !== "undefined" ? window : globalThis);
