/*
 * IndexedDB storage layer. Raw IndexedDB API, no wrapper library — consistent
 * with the rest of this project's no-build-step approach. Promise-based so the
 * rest of the app never touches IDBRequest directly.
 *
 * Schema (db "liftlog", version 1):
 *   exerciseState  keyPath "exercise_id"        — current progression state, one row per exercise
 *   setLogs        autoIncrement "id"           — one row per logged set, indexed on exercise_id and date
 *   meta           keyPath "key"                — {key, value} pairs: lastRotationDay, gymProfile
 *
 * exportAll() is the "automatic JSON export from day one" capability CLAUDE.md
 * asks for — present from the start, triggered by an explicit user action (a real
 * file-save prompt needs a user gesture on mobile anyway, so this isn't a silent
 * background write).
 */

(function (global) {
  "use strict";

  const DB_NAME = "liftlog";
  const DB_VERSION = 1;

  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains("exerciseState")) {
          db.createObjectStore("exerciseState", { keyPath: "exercise_id" });
        }
        if (!db.objectStoreNames.contains("setLogs")) {
          const store = db.createObjectStore("setLogs", { keyPath: "id", autoIncrement: true });
          store.createIndex("by_exercise", "exercise_id");
          store.createIndex("by_date", "date");
        }
        if (!db.objectStoreNames.contains("meta")) {
          db.createObjectStore("meta", { keyPath: "key" });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function tx(db, storeNames, mode, work) {
    return new Promise((resolve, reject) => {
      const t = db.transaction(storeNames, mode);
      let result;
      Promise.resolve(work(t)).then((r) => { result = r; }).catch(reject);
      t.oncomplete = () => resolve(result);
      t.onerror = () => reject(t.error);
      t.onabort = () => reject(t.error);
    });
  }

  function reqToPromise(req) {
    return new Promise((resolve, reject) => {
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  // ---------------------------------------------------------------- exerciseState

  async function getState(exerciseId) {
    const db = await openDB();
    return tx(db, "exerciseState", "readonly", (t) =>
      reqToPromise(t.objectStore("exerciseState").get(exerciseId))
    ).then((r) => r || null);
  }

  async function saveState(state) {
    const db = await openDB();
    return tx(db, "exerciseState", "readwrite", (t) =>
      reqToPromise(t.objectStore("exerciseState").put(state))
    );
  }

  async function getAllStates() {
    const db = await openDB();
    return tx(db, "exerciseState", "readonly", (t) =>
      reqToPromise(t.objectStore("exerciseState").getAll())
    );
  }

  // ---------------------------------------------------------------- setLogs

  // `sets`: array of SetLog-shaped objects (see js/engine.js). Stamps each with
  // exercise_id + date so a flat store can answer "logs for this exercise" and
  // "logs on this date" without a separate sessions table.
  async function appendSetLogs(exerciseId, dateIso, sets) {
    const db = await openDB();
    return tx(db, "setLogs", "readwrite", async (t) => {
      const store = t.objectStore("setLogs");
      for (const s of sets) {
        store.add(Object.assign({}, s, { exercise_id: exerciseId, date: dateIso }));
      }
    });
  }

  async function getSetLogsForExercise(exerciseId) {
    const db = await openDB();
    return tx(db, "setLogs", "readonly", (t) =>
      reqToPromise(t.objectStore("setLogs").index("by_exercise").getAll(exerciseId))
    );
  }

  async function getAllSetLogs() {
    const db = await openDB();
    return tx(db, "setLogs", "readonly", (t) =>
      reqToPromise(t.objectStore("setLogs").getAll())
    );
  }

  // ---------------------------------------------------------------- meta

  async function getMeta(key, fallback = null) {
    const db = await openDB();
    const row = await tx(db, "meta", "readonly", (t) =>
      reqToPromise(t.objectStore("meta").get(key))
    );
    return row ? row.value : fallback;
  }

  async function setMeta(key, value) {
    const db = await openDB();
    return tx(db, "meta", "readwrite", (t) =>
      reqToPromise(t.objectStore("meta").put({ key, value }))
    );
  }

  async function getGymProfile() {
    return getMeta("gymProfile", { has_rack_safeties: false, dumbbell_max: null });
  }

  async function setGymProfile(profile) {
    return setMeta("gymProfile", profile);
  }

  async function getLastRotationDay() {
    return getMeta("lastRotationDay", null);
  }

  async function setLastRotationDay(day) {
    return setMeta("lastRotationDay", day);
  }

  // ---------------------------------------------------------------- export

  async function exportAll() {
    const [exerciseState, setLogs, gymProfile, lastRotationDay] = await Promise.all([
      getAllStates(), getAllSetLogs(), getGymProfile(), getLastRotationDay(),
    ]);
    return {
      schema: 1,
      exported_at: new Date().toISOString(),
      exerciseState,
      setLogs,
      meta: { gymProfile, lastRotationDay },
    };
  }

  // Triggers a real browser save prompt via a Blob + temporary <a download>.
  // Needs a user gesture (call this from a click handler), which is fine — v1's
  // export is an explicit action, not a silent background write.
  async function downloadExport() {
    const data = await exportAll();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `liftlog-backup-${data.exported_at.slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  global.Storage = {
    getState, saveState, getAllStates,
    appendSetLogs, getSetLogsForExercise, getAllSetLogs,
    getMeta, setMeta, getGymProfile, setGymProfile, getLastRotationDay, setLastRotationDay,
    exportAll, downloadExport,
  };
})(typeof window !== "undefined" ? window : globalThis);
