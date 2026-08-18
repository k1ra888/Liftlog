/*
 * Progression engine — JS port of engine/progression.py, engine/safety.py, and
 * engine/models.py. Python is the spec (see CLAUDE.md); this mirrors it
 * function-for-function and name-for-name (camelCase for functions, but object
 * FIELD KEYS stay snake_case to match the Python dataclass field names exactly —
 * that's deliberate, not a style slip, and is what keeps parity/harness.html's
 * comparisons trivial instead of needing a translation layer).
 *
 * No build step, no ES modules (file:// blocks module imports via CORS) — this
 * attaches everything to a single global, `Engine`, loaded via a plain
 * <script src="js/engine.js"> tag.
 *
 * Deliberately NOT ported 1:1: the free-text message/notes/advice strings.
 * Those are presentation, not logic — the parity harness checks the structured
 * fields (diagnosis, next_weight, next_rep_target, counters, prescriptions,
 * safety-floor values, volume numbers), not English wording. See parity/harness.html.
 */

(function (global) {
  "use strict";

  // ---------------------------------------------------------------- enums
  // Python's `str, Enum` members serialize as their .value string — so these are
  // just the value strings directly, no wrapper needed.

  const Equipment = Object.freeze({
    BARBELL: "barbell",
    DUMBBELL: "dumbbell",
    MACHINE: "machine",
    CABLE: "cable",
    BODYWEIGHT: "bodyweight",
  });

  const FailureRisk = Object.freeze({
    SAFE_TO_FAILURE: "safe_to_failure",
    BAILOUT_POSSIBLE: "bailout_possible",
    NEEDS_SAFETIES: "needs_safeties",
  });

  const CapReason = Object.freeze({
    NONE: "none",
    SOLO_NO_SAFETIES: "solo_no_safeties",
    SOLO_BAILOUT: "solo_bailout",
  });

  const Outcome = Object.freeze({
    HIT: "hit",
    PARTIAL: "partial",
    MISS: "miss",
    FIRST_TIME: "first_time",
  });

  const Diagnosis = Object.freeze({
    PROGRESS_REPS: "progress_reps",
    PROGRESS_LOAD: "progress_load",
    HOLD_CONSOLIDATE: "hold_consolidate",
    REPEAT_TOO_HEAVY: "repeat_too_heavy",
    REPEAT_FATIGUE: "repeat_fatigue",
    STALL_INTERVENTION: "stall_intervention",
    FIRST_TIME: "first_time",
  });

  // ---------------------------------------------------------------- factories
  // Plain objects with the same defaults as the Python dataclasses.

  function exercise({
    id, name, primary_muscles, secondary_muscles = [], rep_range = [8, 12],
    load_increment = 2.5, equipment = Equipment.BARBELL,
    failure_risk = FailureRisk.SAFE_TO_FAILURE, substitutes = [],
    default_rest_seconds = 120, is_bodyweight = false,
  }) {
    return {
      id, name, primary_muscles, secondary_muscles, rep_range, load_increment,
      equipment, failure_risk, substitutes, default_rest_seconds, is_bodyweight,
    };
  }

  function gymProfile({ has_rack_safeties = false, has_smith_machine = false, dumbbell_max = null } = {}) {
    return { has_rack_safeties, has_smith_machine, dumbbell_max };
  }

  function setPrescription({
    set_index, target_weight, target_reps, target_rir, capped = false,
    cap_reason = CapReason.NONE, rest_seconds = 120,
  }) {
    return { set_index, target_weight, target_reps, target_rir, capped, cap_reason, rest_seconds };
  }

  function setLog({
    set_index, weight, reps, rir = null, target_weight = 0.0, target_reps = 0,
    target_rir = 0, stopped_at_cap = false, is_warmup = false,
  }) {
    return { set_index, weight, reps, rir, target_weight, target_reps, target_rir, stopped_at_cap, is_warmup };
  }

  function exerciseState({
    exercise_id, current_weight, current_rep_target, consecutive_stalls = 0,
    consecutive_fatigue = 0, last_performed_date = null, observed_dropoff = null,
  }) {
    return {
      exercise_id, current_weight, current_rep_target, consecutive_stalls,
      consecutive_fatigue, last_performed_date, observed_dropoff,
    };
  }

  function decision({
    diagnosis, next_weight, next_rep_target, consecutive_stalls, message,
    consecutive_fatigue = 0, notes = [], intervention_options = [],
  }) {
    return {
      diagnosis, next_weight, next_rep_target, consecutive_stalls, message,
      consecutive_fatigue, notes, intervention_options,
    };
  }

  // ---------------------------------------------------------------- constants
  // Copied as literals, not re-derived — same reasoning as the Python comments:
  // 1 - 0.9 in floating point is 0.09999999999999998, which floored to the wrong
  // step and silently deloaded 100 lb to 92.5 instead of 90. Store the drop itself.

  // Reps as a proportion of set 1, for sets taken TO FAILURE at a fixed load.
  // Anomaly band only — never a prescription. See evidence-base.md §11.
  const FAILURE_DROPOFF_BAND = [1.00, 0.70, 0.55, 0.50, 0.45];

  const LAYOFF_DAYS = 14;
  const LAYOFF_DROP = 0.10;
  const STALL_DROP = 0.10;
  const STALL_THRESHOLD = 3;
  const FATIGUE_PATIENCE = 2;
  const RIR_TRUST_CAP = 3;

  // ---------------------------------------------------------------- helpers

  // Python's round() is round-half-to-even (banker's rounding); JS's Math.round()
  // rounds half away from zero. Weights land exactly on a .5-step boundary often
  // enough (e.g. 105 / 10 = 10.5 exactly) that this divergence is real, not
  // theoretical — pyRound() replicates Python 3's behavior for non-negative inputs
  // (every value in this domain — weights, set indices, rep counts — is >= 0).
  function pyRound(value, ndigits = 0) {
    const factor = Math.pow(10, ndigits);
    const scaled = value * factor;
    const floor = Math.floor(scaled);
    const diff = scaled - floor;
    const EPS = 1e-9;
    let rounded;
    if (Math.abs(diff - 0.5) < EPS) {
      rounded = floor % 2 === 0 ? floor : floor + 1;
    } else {
      rounded = Math.round(scaled);
    }
    return rounded / factor;
  }

  function roundToIncrement(weight, increment, down = false) {
    if (increment <= 0) return pyRound(weight, 2);
    const steps = weight / increment;
    const roundedSteps = down ? Math.floor(steps) : pyRound(steps);
    return pyRound(roundedSteps * increment, 2);
  }

  function rirRamp(numSets) {
    if (numSets <= 0) return [];
    if (numSets === 1) return [0];
    if (numSets === 2) return [1, 0];
    return [2, ...Array(numSets - 2).fill(1), 0];
  }

  function workingSets(sets) {
    return sets.filter((s) => !s.is_warmup).slice().sort((a, b) => a.set_index - b.set_index);
  }

  // Days between two ISO "YYYY-MM-DD" date strings, parsed as UTC so local
  // timezone offsets can't shift the day count by one.
  function daysBetween(isoA, isoB) {
    const a = Date.parse(isoA + "T00:00:00Z");
    const b = Date.parse(isoB + "T00:00:00Z");
    return Math.round((b - a) / 86400000);
  }

  // ---------------------------------------------------------------- safety (safety.py)

  function rirFloor(ex, gym, spotterPresent) {
    if (ex.failure_risk === FailureRisk.SAFE_TO_FAILURE) {
      return [0, CapReason.NONE, ""];
    }
    if (spotterPresent) {
      return [0, CapReason.NONE, ""];
    }
    if (ex.failure_risk === FailureRisk.NEEDS_SAFETIES) {
      if (gym.has_rack_safeties) {
        return [0, CapReason.NONE, "Set the rack pins at chest height before you start."];
      }
      let advice =
        `Training alone on ${ex.name} with no safeties — capped at RIR 1. ` +
        "Setting rack pins removes this cap entirely at no cost to the stimulus.";
      if (ex.substitutes.length) {
        advice += ` Safer alternatives: ${ex.substitutes.join(", ")}.`;
      }
      return [1, CapReason.SOLO_NO_SAFETIES, advice];
    }
    // BAILOUT_POSSIBLE
    return [0, CapReason.SOLO_BAILOUT,
      `Training alone on ${ex.name}. Failing is recoverable, but know how to bail before your last set.`];
  }

  // ---------------------------------------------------------------- prescribe

  function prescribe(ex, state, numSets, gym, spotterPresent, today) {
    if (state === null || state === undefined) return [];

    let weight = state.current_weight;
    const reps = state.current_rep_target;

    if (state.last_performed_date !== null && state.last_performed_date !== undefined) {
      if (daysBetween(state.last_performed_date, today) > LAYOFF_DAYS) {
        const drop = roundToIncrement(weight * LAYOFF_DROP, ex.load_increment, true);
        weight = pyRound(weight - Math.max(drop, ex.load_increment), 2);
      }
    }

    const [floor, capReason] = rirFloor(ex, gym, spotterPresent);
    const ramp = rirRamp(numSets);

    return ramp.map((naturalRir, i) => {
      const effectiveRir = Math.max(naturalRir, floor);
      const capped = effectiveRir > naturalRir;
      return setPrescription({
        set_index: i + 1,
        target_weight: weight,
        target_reps: reps,
        target_rir: effectiveRir,
        capped,
        cap_reason: capped ? capReason : CapReason.NONE,
        rest_seconds: ex.default_rest_seconds,
      });
    });
  }

  // ---------------------------------------------------------------- classify

  function classify(sets) {
    const ws = workingSets(sets);
    if (ws.length === 0) return Outcome.FIRST_TIME;

    const first = ws[0];
    if (first.reps < first.target_reps || first.weight < first.target_weight) {
      return Outcome.MISS;
    }
    for (const s of ws.slice(1)) {
      if (s.reps < s.target_reps || s.weight < s.target_weight) {
        return Outcome.PARTIAL;
      }
    }
    return Outcome.HIT;
  }

  function dropoffNotes(sets) {
    const ws = workingSets(sets);
    const notes = [];
    if (ws.length < 2 || ws[0].reps === 0) return notes;

    const base = ws[0].reps;
    for (const s of ws.slice(1)) {
      const idx = s.set_index - 1;
      if (idx >= FAILURE_DROPOFF_BAND.length) continue;
      const ratio = s.reps / base;
      if (ratio < FAILURE_DROPOFF_BAND[idx]) {
        const pct = pyRound(ratio * 100, 0);
        notes.push(
          `Set ${s.set_index} fell to ${pct}% of set 1 — steeper than typical ` +
          "even for sets taken to failure. Try longer rest before cutting the load."
        );
      }
    }
    return notes;
  }

  // ---------------------------------------------------------------- progress

  // Returns [rirUsed, treatAsHadMore]. A capped RIR 1 means "I had more and was
  // told to stop" -> progress. An uncapped RIR 1 means "that was nearly
  // everything" -> hold. Identical logged value, opposite correct action.
  function conditionRir(s) {
    if (s.stopped_at_cap) return [1, true];
    if (s.rir === null || s.rir === undefined) return [2, false];
    return [Math.min(s.rir, RIR_TRUST_CAP), false];
  }

  function progress(ex, state, sets, today) {
    const ws = workingSets(sets);
    if (ws.length === 0) {
      return decision({
        diagnosis: Diagnosis.FIRST_TIME,
        next_weight: state.current_weight,
        next_rep_target: state.current_rep_target,
        consecutive_stalls: state.consecutive_stalls,
        message: "No working sets logged.",
      });
    }

    const first = ws[0];
    const outcome = classify(ws);
    const [lo, hi] = ex.rep_range;
    const inc = (ex.is_bodyweight && first.weight === 0) ? 0.0 : ex.load_increment;
    const weight = first.target_weight || first.weight;
    const reps = first.target_reps || state.current_rep_target;
    let stalls = state.consecutive_stalls;
    const notes = dropoffNotes(ws);

    // --- set 1 missed: the load is too heavy. This is the only strength signal.
    if (outcome === Outcome.MISS) {
      stalls += 1;
      if (stalls >= STALL_THRESHOLD) {
        const stepDown = Math.max(roundToIncrement(weight * STALL_DROP, inc || 2.5, true), inc || 2.5);
        const options = [`Drop to ${pyRound(weight - stepDown, 2)} and rebuild`];
        if (ex.substitutes.length) {
          options.push(`Swap to: ${ex.substitutes.join(", ")}`);
        }
        return decision({
          diagnosis: Diagnosis.STALL_INTERVENTION,
          next_weight: weight,
          next_rep_target: reps,
          consecutive_stalls: stalls,
          message: `Stalled ${stalls} sessions on ${ex.name}. Pick an intervention — nothing is applied automatically.`,
          notes,
          intervention_options: options,
        });
      }
      return decision({
        diagnosis: Diagnosis.REPEAT_TOO_HEAVY,
        next_weight: weight,
        next_rep_target: reps,
        consecutive_stalls: stalls,
        message: `Set 1 fell short — repeat ${weight} for ${reps}. Stall ${stalls}/${STALL_THRESHOLD}.`,
        notes,
      });
    }

    // --- set 1 hit, later sets faded: fatigue or recovery, NOT strength.
    if (outcome === Outcome.PARTIAL) {
      const fatigue = state.consecutive_fatigue + 1;
      if (fatigue <= FATIGUE_PATIENCE) {
        return decision({
          diagnosis: Diagnosis.REPEAT_FATIGUE,
          next_weight: weight,
          next_rep_target: reps,
          consecutive_stalls: stalls,
          consecutive_fatigue: fatigue,
          message: `Set 1 hit but later sets faded on ${ex.name}. That is fatigue, not a strength problem — hold ${weight} and lengthen rest before cutting load.`,
          notes,
        });
      }
      // Persistent, not transient — progress on set 1's merit rather than holding forever.
      notes.push(
        `Later sets have faded ${fatigue} sessions running while set 1 kept hitting. ` +
        "That is normal within-session fatigue, not a plateau — progressing on set 1 " +
        "and relaxing the later-set targets."
      );
      notes.push(
        "This is the case fitted per-set decay targets are meant to handle properly " +
        "(v1.1); flat targets across sets cannot represent it."
      );
    }

    // --- clean hit (or persistent-fatigue fallthrough). Read effort from set 1.
    stalls = 0;
    let [rirUsed, hadMore] = conditionRir(first);

    if (hadMore) {
      notes.push("Set 1 was cap-limited, so its RIR is a ceiling, not a true effort reading.");
      rirUsed = 2;
    }

    if (rirUsed === 0) {
      notes.push(
        "Set 1 reached failure — that costs reps on every later set. The target was " +
        "set too aggressively; holding here rather than adding load."
      );
      return decision({
        diagnosis: Diagnosis.HOLD_CONSOLIDATE,
        next_weight: weight,
        next_rep_target: reps,
        consecutive_stalls: stalls,
        consecutive_fatigue: 0,
        message: `Hold ${weight} × ${reps}. Consolidate before progressing.`,
        notes,
      });
    }

    const step = rirUsed >= RIR_TRUST_CAP ? 2 : 1;

    if (reps + step <= hi) {
      if (rirUsed >= RIR_TRUST_CAP) {
        notes.push("Reported RIR 3+ is low-confidence, so moving by reps rather than a load jump.");
      }
      return decision({
        diagnosis: Diagnosis.PROGRESS_REPS,
        next_weight: weight,
        next_rep_target: reps + step,
        consecutive_stalls: stalls,
        consecutive_fatigue: 0,
        message: `Next time: ${weight} × ${reps + step}.`,
        notes,
      });
    }

    if (inc === 0.0) {
      return decision({
        diagnosis: Diagnosis.PROGRESS_REPS,
        next_weight: weight,
        next_rep_target: reps + step,
        consecutive_stalls: stalls,
        consecutive_fatigue: 0,
        message: `Next time: bodyweight × ${reps + step}.`,
        notes,
      });
    }

    // Add the increment to the CURRENT weight — never re-round onto an absolute
    // grid. See progression.py's comment; this is bug #3 from CLAUDE.md.
    const newWeight = pyRound(weight + inc, 2);
    return decision({
      diagnosis: Diagnosis.PROGRESS_LOAD,
      next_weight: newWeight,
      next_rep_target: lo,
      consecutive_stalls: stalls,
      consecutive_fatigue: 0,
      message: `Top of the rep range — next time: ${newWeight} × ${lo}.`,
      notes,
    });
  }

  function apply(state, dec, today) {
    return exerciseState({
      exercise_id: state.exercise_id,
      current_weight: dec.next_weight,
      current_rep_target: dec.next_rep_target,
      consecutive_stalls: dec.consecutive_stalls,
      consecutive_fatigue: dec.consecutive_fatigue,
      last_performed_date: today,
      observed_dropoff: state.observed_dropoff,
    });
  }

  function bootstrap(ex, firstLog, today) {
    const [lo, hi] = ex.rep_range;
    const reps = Math.max(lo, Math.min(firstLog.reps, hi));
    return exerciseState({
      exercise_id: ex.id,
      current_weight: firstLog.weight,
      current_rep_target: reps,
      last_performed_date: today,
    });
  }

  // ---------------------------------------------------------------- exports

  global.Engine = {
    Equipment, FailureRisk, CapReason, Outcome, Diagnosis,
    exercise, gymProfile, setPrescription, setLog, exerciseState, decision,
    FAILURE_DROPOFF_BAND, LAYOFF_DAYS, LAYOFF_DROP, STALL_DROP, STALL_THRESHOLD,
    FATIGUE_PATIENCE, RIR_TRUST_CAP,
    pyRound, roundToIncrement, rirRamp, workingSets, daysBetween,
    rirFloor, prescribe, classify, dropoffNotes, progress, apply, bootstrap,
  };
})(typeof window !== "undefined" ? window : globalThis);
