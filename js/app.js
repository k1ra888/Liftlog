/*
 * UI wiring. Talks to Engine (decision logic), Library (exercise data), and
 * Storage (IndexedDB) — never contains decision logic itself. If a rule about
 * what to prescribe or how to progress needs to change, it changes in
 * js/engine.js (and engine/progression.py first), not here.
 */

(function () {
  "use strict";

  const NUM_SETS = 3;

  // name -> Exercise, for resolving `substitutes` (stored as display names in the
  // Python data, ported as-is) to real exercise objects for the swap picker.
  const EXERCISE_BY_NAME = {};
  for (const ex of Library.EXERCISE_LIBRARY) EXERCISE_BY_NAME[ex.name] = ex;

  function todayIso() {
    return new Date().toISOString().slice(0, 10);
  }

  function dayRoster(day) {
    if (day === "push") return Library.PUSH_DAY_SESSION;
    if (day === "pull") return Library.PULL_DAY;
    if (day === "legs") return Library.LEG_DAY;
    return [];
  }

  // ---------------------------------------------------------------- app state

  const state = {
    view: "log",
    day: null,
    daySlots: [],          // this session's exercise per slot (post-swap), same order as dayRoster(day)
    loggedTodayIds: new Set(),
    gymProfile: { has_rack_safeties: false, dumbbell_max: null },
  };

  // ---------------------------------------------------------------- bootstrap

  async function init() {
    state.gymProfile = await Storage.getGymProfile();
    const last = await Storage.getLastRotationDay();
    state.day = Library.nextInRotation(last);
    state.daySlots = dayRoster(state.day).slice();

    await refreshLoggedToday();
    renderDayChip();
    renderExerciseList();
    await renderNumbers();
    wireNav();
    wireDayPicker();
    wireSettings();
    wireOverlayClose();
    registerServiceWorker();
  }

  async function refreshLoggedToday() {
    state.loggedTodayIds = new Set();
    const today = todayIso();
    for (const ex of state.daySlots) {
      const logs = await Storage.getSetLogsForExercise(ex.id);
      if (logs.some((l) => l.date === today)) state.loggedTodayIds.add(ex.id);
    }
  }

  function registerServiceWorker() {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("./sw.js").catch(() => {
        // Offline install just won't work this session — logging itself doesn't
        // depend on it, so this is deliberately non-fatal.
      });
    }
  }

  // ---------------------------------------------------------------- nav

  function wireNav() {
    document.getElementById("nav-log").addEventListener("click", () => setView("log"));
    document.getElementById("nav-numbers").addEventListener("click", () => setView("numbers"));
  }

  function setView(view) {
    state.view = view;
    document.getElementById("view-log").classList.toggle("hidden", view !== "log");
    document.getElementById("view-numbers").classList.toggle("hidden", view !== "numbers");
    document.getElementById("nav-log").classList.toggle("active", view === "log");
    document.getElementById("nav-numbers").classList.toggle("active", view === "numbers");
    if (view === "numbers") renderNumbers();
  }

  // ---------------------------------------------------------------- day picker

  function wireDayPicker() {
    document.getElementById("day-change-btn").addEventListener("click", () => {
      const box = document.getElementById("day-picker-options");
      box.classList.toggle("hidden");
      if (!box.classList.contains("hidden")) {
        box.innerHTML = "";
        for (const d of ["push", "pull", "legs", "rest"]) {
          const btn = document.createElement("button");
          btn.textContent = d;
          btn.addEventListener("click", async () => {
            state.day = d;
            state.daySlots = dayRoster(d).slice();
            await Storage.setLastRotationDay(d);
            await refreshLoggedToday();
            renderDayChip();
            renderExerciseList();
            box.classList.add("hidden");
          });
          box.appendChild(btn);
        }
      }
    });
  }

  function renderDayChip() {
    document.getElementById("day-chip").textContent = state.day;
  }

  // ---------------------------------------------------------------- exercise list

  function renderExerciseList() {
    const list = document.getElementById("exercise-list");
    list.innerHTML = "";

    if (state.day === "rest") {
      const card = document.createElement("div");
      card.className = "card";
      card.textContent = "Rest day — nothing scheduled.";
      list.appendChild(card);
      return;
    }

    state.daySlots.forEach((ex, slotIndex) => {
      const card = document.createElement("div");
      card.className = "card exercise-card";
      card.setAttribute("role", "button");
      card.tabIndex = 0;

      const left = document.createElement("div");
      const name = document.createElement("div");
      name.className = "ex-name";
      name.textContent = ex.name;
      const meta = document.createElement("div");
      meta.className = "ex-meta";
      meta.textContent = `${ex.rep_range[0]}–${ex.rep_range[1]} reps`;
      left.appendChild(name);
      left.appendChild(meta);
      if (state.loggedTodayIds.has(ex.id)) {
        const status = document.createElement("div");
        status.className = "ex-status";
        status.textContent = "✓ logged today";
        left.appendChild(status);
      }

      card.appendChild(left);
      card.addEventListener("click", () => openExerciseIntro(slotIndex));
      list.appendChild(card);
    });
  }

  // ---------------------------------------------------------------- exercise overlay

  const overlay = document.getElementById("exercise-overlay");
  const overlayTitle = document.getElementById("overlay-title");
  const overlayBody = document.getElementById("overlay-body");
  const overlaySwap = document.getElementById("overlay-swap");

  function wireOverlayClose() {
    document.getElementById("overlay-close").addEventListener("click", closeOverlay);
    document.getElementById("settings-close").addEventListener("click", () =>
      document.getElementById("settings-overlay").classList.add("hidden")
    );
  }

  function closeOverlay() {
    overlay.classList.add("hidden");
    overlaySwap.classList.add("hidden");
    overlaySwap.onclick = null;
  }

  // session holds everything needed across the multi-step logging flow for one
  // exercise: which slot it came from (so a swap persists back into daySlots),
  // the exercise itself, prior state, the plan (or null if first-time), and the
  // sets logged so far this session.
  let session = null;

  async function openExerciseIntro(slotIndex) {
    const ex = state.daySlots[slotIndex];
    const priorState = await Storage.getState(ex.id);
    session = { slotIndex, ex, priorState, plan: null, sets: [], setIndex: 0 };

    overlayTitle.textContent = ex.name;
    overlay.classList.remove("hidden");

    if (ex.substitutes.length) {
      overlaySwap.classList.remove("hidden");
      overlaySwap.onclick = () => openSwapPicker(ex);
    } else {
      overlaySwap.classList.add("hidden");
    }

    renderIntro();
  }

  function openSwapPicker(ex) {
    overlayBody.innerHTML = "";
    const heading = document.createElement("p");
    heading.className = "target-row";
    heading.textContent = "Swap to for today's session:";
    overlayBody.appendChild(heading);

    for (const name of ex.substitutes) {
      const alt = EXERCISE_BY_NAME[name];
      if (!alt) continue;
      const btn = document.createElement("button");
      btn.className = "btn btn-secondary btn-block";
      btn.style.marginBottom = "10px";
      btn.textContent = name;
      btn.addEventListener("click", () => {
        state.daySlots[session.slotIndex] = alt;
        openExerciseIntro(session.slotIndex);
      });
      overlayBody.appendChild(btn);
    }

    const back = document.createElement("button");
    back.className = "link-btn";
    back.textContent = "cancel";
    back.addEventListener("click", () => renderIntro());
    overlayBody.appendChild(back);
  }

  function spotterMatters(ex) {
    return ex.failure_risk === Engine.FailureRisk.NEEDS_SAFETIES && !state.gymProfile.has_rack_safeties;
  }

  function renderIntro() {
    const { ex, priorState } = session;
    overlayBody.innerHTML = "";

    if (priorState) {
      session.plan = Engine.prescribe(
        ex, priorState, NUM_SETS, Engine.gymProfile(state.gymProfile),
        session.spotterPresent === true, todayIso()
      );
      const planCard = document.createElement("div");
      planCard.className = "card";
      session.plan.forEach((p) => {
        const row = document.createElement("div");
        row.className = "target-row";
        row.innerHTML = `Set ${p.set_index}: <strong>${p.target_weight} lb × ${p.target_reps}</strong> · RIR ${p.target_rir}` +
          (p.capped ? ' <span class="badge-cap">capped</span>' : "");
        planCard.appendChild(row);
      });
      overlayBody.appendChild(planCard);
    } else {
      const note = document.createElement("div");
      note.className = "card";
      note.textContent = "First time logging this — no targets yet. Log what you do; next session's plan starts from this.";
      overlayBody.appendChild(note);
      session.plan = null;
    }

    if (spotterMatters(ex)) {
      const row = document.createElement("label");
      row.className = "settings-row";
      row.innerHTML = `<span>Spotter present this session</span>`;
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "toggle";
      cb.checked = session.spotterPresent === true;
      cb.addEventListener("change", () => {
        session.spotterPresent = cb.checked;
        renderIntro();
      });
      row.appendChild(cb);
      overlayBody.appendChild(row);
    }

    const start = document.createElement("button");
    start.className = "btn btn-primary btn-block";
    start.textContent = "Start";
    start.addEventListener("click", () => {
      session.setIndex = 0;
      session.sets = [];
      renderSetEntry();
    });
    overlayBody.appendChild(start);
  }

  // ---------------------------------------------------------------- per-set logging

  function renderSetEntry() {
    overlaySwap.classList.add("hidden");
    const { ex, plan, setIndex } = session;
    const target = plan ? plan[setIndex] : null;

    const startWeight = target ? target.target_weight : (session.sets.length ? session.sets[session.sets.length - 1].weight : 0);
    const startReps = target ? target.target_reps : (session.sets.length ? session.sets[session.sets.length - 1].reps : 8);
    const startRir = target ? target.target_rir : 2;
    const weightStep = ex.load_increment || 5;

    overlayBody.innerHTML = "";

    const card = document.createElement("div");
    card.className = "card set-card";

    const title = document.createElement("div");
    title.className = "set-title";
    title.innerHTML = `Set ${setIndex + 1} of ${NUM_SETS}` +
      (target && target.capped ? ' <span class="badge-cap">capped</span>' : "");
    card.appendChild(title);

    if (target) {
      const tr = document.createElement("div");
      tr.className = "target-row";
      tr.textContent = `Target: ${target.target_weight} lb × ${target.target_reps} · RIR ${target.target_rir}`;
      card.appendChild(tr);
    }

    const values = { weight: startWeight, reps: startReps, rir: startRir };

    const group = document.createElement("div");
    group.className = "stepper-group";
    group.appendChild(makeStepper("Weight", values, "weight", weightStep, 0, null));
    group.appendChild(makeStepper("Reps", values, "reps", 1, 0, null));
    group.appendChild(makeStepper("RIR", values, "rir", 1, 0, 5));
    card.appendChild(group);

    const logBtn = document.createElement("button");
    logBtn.className = "btn btn-primary btn-block";
    logBtn.textContent = setIndex === NUM_SETS - 1 ? "Log final set" : "Log set";
    logBtn.addEventListener("click", () => {
      session.sets.push(Engine.setLog({
        set_index: setIndex + 1,
        weight: values.weight,
        reps: values.reps,
        rir: values.rir,
        target_weight: target ? target.target_weight : 0,
        target_reps: target ? target.target_reps : 0,
        target_rir: target ? target.target_rir : 0,
        stopped_at_cap: target ? target.capped : false,
      }));
      if (setIndex + 1 < NUM_SETS) {
        session.setIndex += 1;
        renderRestTimer(ex.default_rest_seconds);
      } else {
        finishExercise();
      }
    });
    card.appendChild(logBtn);

    overlayBody.appendChild(card);
  }

  function makeStepper(label, values, key, step, min, max) {
    const wrap = document.createElement("div");
    wrap.className = "stepper";
    const lbl = document.createElement("div");
    lbl.className = "stepper-label";
    lbl.textContent = label;
    wrap.appendChild(lbl);

    const controls = document.createElement("div");
    controls.className = "stepper-controls";

    const minus = document.createElement("button");
    minus.textContent = "−";
    const val = document.createElement("div");
    val.className = "stepper-value";
    val.textContent = values[key];
    const plus = document.createElement("button");
    plus.textContent = "+";

    function clamp(v) {
      if (min !== null && v < min) return min;
      if (max !== null && v > max) return max;
      return Math.round(v * 100) / 100;
    }

    minus.addEventListener("click", () => {
      values[key] = clamp(values[key] - step);
      val.textContent = values[key];
    });
    plus.addEventListener("click", () => {
      values[key] = clamp(values[key] + step);
      val.textContent = values[key];
    });

    controls.appendChild(minus);
    controls.appendChild(val);
    controls.appendChild(plus);
    wrap.appendChild(controls);
    return wrap;
  }

  // ---------------------------------------------------------------- rest timer

  function renderRestTimer(seconds) {
    overlayBody.innerHTML = "";
    const card = document.createElement("div");
    card.className = "card timer";
    const label = document.createElement("div");
    label.className = "timer-label";
    label.textContent = "Rest";
    const value = document.createElement("div");
    value.className = "timer-value";
    card.appendChild(label);
    card.appendChild(value);

    const skip = document.createElement("button");
    skip.className = "btn btn-secondary btn-block";
    skip.textContent = "Skip rest";
    skip.style.marginTop = "16px";

    overlayBody.appendChild(card);
    overlayBody.appendChild(skip);

    let remaining = seconds;
    function tick() {
      const m = Math.floor(remaining / 60);
      const s = remaining % 60;
      value.textContent = `${m}:${String(s).padStart(2, "0")}`;
    }
    tick();
    const interval = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearInterval(interval);
        renderSetEntry();
        return;
      }
      tick();
    }, 1000);

    skip.addEventListener("click", () => {
      clearInterval(interval);
      renderSetEntry();
    });
  }

  // ---------------------------------------------------------------- finish

  async function finishExercise() {
    const { ex, priorState, sets } = session;
    const today = todayIso();

    overlayBody.innerHTML = "";

    if (!priorState) {
      const newState = Engine.bootstrap(ex, sets[0], today);
      await Storage.saveState(newState);
      await Storage.appendSetLogs(ex.id, today, sets);

      const card = document.createElement("div");
      card.className = "card decision-card";
      const msg = document.createElement("div");
      msg.className = "decision-message";
      msg.textContent = `Logged. Starting point for next time: ${newState.current_weight} lb × ${newState.current_rep_target}.`;
      card.appendChild(msg);
      overlayBody.appendChild(card);
    } else {
      const dec = Engine.progress(ex, priorState, sets, today);
      const newState = Engine.apply(priorState, dec, today);
      await Storage.saveState(newState);
      await Storage.appendSetLogs(ex.id, today, sets);

      const card = document.createElement("div");
      card.className = "card decision-card";

      const diag = document.createElement("div");
      diag.className = "decision-diagnosis";
      diag.textContent = dec.diagnosis.replace(/_/g, " ");
      card.appendChild(diag);

      const msg = document.createElement("div");
      msg.className = "decision-message";
      msg.textContent = dec.message;
      card.appendChild(msg);

      for (const note of dec.notes) {
        const n = document.createElement("div");
        n.className = "decision-note";
        n.textContent = note;
        card.appendChild(n);
      }
      overlayBody.appendChild(card);

      if (dec.intervention_options.length) {
        const optWrap = document.createElement("div");
        optWrap.className = "intervention-options";
        const heading = document.createElement("div");
        heading.className = "target-row";
        heading.textContent = "Pick an option — nothing applied automatically:";
        optWrap.appendChild(heading);
        for (const opt of dec.intervention_options) {
          const btn = document.createElement("button");
          btn.className = "btn btn-secondary";
          btn.textContent = opt;
          btn.addEventListener("click", () => btn.classList.add("btn-primary"));
          optWrap.appendChild(btn);
        }
        overlayBody.appendChild(optWrap);
      }
    }

    const done = document.createElement("button");
    done.className = "btn btn-primary btn-block";
    done.style.marginTop = "16px";
    done.textContent = "Done";
    done.addEventListener("click", async () => {
      closeOverlay();
      await refreshLoggedToday();
      renderExerciseList();
    });
    overlayBody.appendChild(done);
  }

  // ---------------------------------------------------------------- numbers view

  async function renderNumbers() {
    const container = document.getElementById("numbers-bars");
    const source = document.getElementById("numbers-source");
    container.innerHTML = "";

    const dayDefs = [
      ["push", Library.PUSH_DAY_SESSION],
      ["pull", Library.PULL_DAY],
      ["legs", Library.LEG_DAY],
    ];

    let usedRealData = false;
    const loggedByDay = {};
    for (const [day, roster] of dayDefs) {
      const entries = [];
      for (const ex of roster) {
        const logs = await Storage.getSetLogsForExercise(ex.id);
        const workingSets = logs.filter((l) => !l.is_warmup);
        if (workingSets.length > 0) {
          // most recent session's set count for this exercise
          const lastDate = workingSets.reduce((a, b) => (a > b.date ? a : b.date), workingSets[0].date);
          const count = workingSets.filter((l) => l.date === lastDate).length;
          entries.push([ex, count]);
          usedRealData = true;
        } else {
          entries.push([ex, 3]); // no history yet — preview assumption, same as routinePreview()
        }
      }
      loggedByDay[day] = entries;
    }

    const volume = Library.rotationVolume(loggedByDay);
    const max = Math.max(...Object.values(volume), 1);

    for (const [muscle, count] of Object.entries(volume)) {
      const row = document.createElement("div");
      row.className = "bar-row";
      const label = document.createElement("div");
      label.className = "bar-label";
      label.innerHTML = `<span>${muscle}</span><span class="bar-value">${count}</span>`;
      const track = document.createElement("div");
      track.className = "bar-track";
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = `${(count / max) * 100}%`;
      track.appendChild(fill);
      row.appendChild(label);
      row.appendChild(track);
      container.appendChild(row);
    }

    source.textContent = usedRealData
      ? "Mixes your most recently logged set counts with a 3-set assumption for exercises you haven't logged yet."
      : "No sessions logged yet — showing a 3-set-per-exercise preview of your current routine.";
  }

  // ---------------------------------------------------------------- settings

  function wireSettings() {
    const overlay = document.getElementById("settings-overlay");
    document.getElementById("settings-btn").addEventListener("click", async () => {
      document.getElementById("setting-rack-safeties").checked = !!state.gymProfile.has_rack_safeties;
      document.getElementById("setting-dumbbell-max").value = state.gymProfile.dumbbell_max || "";
      overlay.classList.remove("hidden");
    });

    document.getElementById("setting-rack-safeties").addEventListener("change", async (e) => {
      state.gymProfile.has_rack_safeties = e.target.checked;
      await Storage.setGymProfile(state.gymProfile);
    });

    document.getElementById("setting-dumbbell-max").addEventListener("change", async (e) => {
      const v = e.target.value === "" ? null : Number(e.target.value);
      state.gymProfile.dumbbell_max = v;
      await Storage.setGymProfile(state.gymProfile);
    });

    document.getElementById("export-btn").addEventListener("click", () => {
      Storage.downloadExport();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
