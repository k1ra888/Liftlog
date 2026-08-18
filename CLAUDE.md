# CLAUDE.md — project context

Handoff document. Read this fully before changing anything.

This project has already been through a research pass and several rounds of design
argument. Most of the non-obvious decisions here were made *against* the conventional
answer, for reasons recorded below. Please do not silently revert them.

---

## What this is

A hypertrophy training app for the owner's Samsung phone. Tracks progressive
overload — but the differentiator is that it **prescribes** the next session rather
than merely recording the last one.

Every training rule must trace to `docs/evidence-base.md`, and must carry its evidence
tier. A lot of what circulates as "science-based lifting" is practitioner framework
with no published validation; the app's honesty about that distinction is a product
requirement, not a nicety.

**Target: installable PWA** (single-file HTML/CSS/JS, offline-first, IndexedDB).
Chosen over native Kotlin because the project's real risk is abandonment, not the
wrong framework — the priority is logging real sets within weeks. Play Store remains
reachable later via a Bubblewrap/TWA wrap.

---

## Owner profile — this drives real code

| | |
|---|---|
| Units | **pounds** |
| Smallest plate | **5 lb** → barbell/Smith moves in **10 lb** steps |
| Split | push / pull / legs / rest, as a **rotation, not a calendar** |
| Gym | commercial, most common machines, Smith machine, cables, fixed-weight bars |
| Trains | alone (spotter availability is a per-session toggle, not a profile field) |
| Coding | basic Python; not a developer. Explain reasoning, don't just ship diffs. |

**Push day** (already seeded in `engine/library.py`): one bench variant (Smith *or*
dumbbell — he alternates), one incline via the same method, standing shoulder press
on fixed-weight bars, cable overhead tricep extension, cable pushdown.

**Pull and legs are not yet specified. This is the blocker for building the UI.**

---

## Evidence base — condensed

Full detail with caveats in `docs/evidence-base.md`. Tiers matter; do not flatten them.

**Tier 1 — build on these**

- **Volume drives hypertrophy with diminishing returns.** [Pelland et al. 2025, *Sports Medicine*](https://link.springer.com/article/10.1007/s40279-025-02344-w) (67 studies, 2,058 participants). Critically: **fractional set counting** — direct sets 1.0, indirect 0.5 — predicted adaptations better than raw totals. This is why every exercise carries `primary_muscles` and `secondary_muscles`. **The paper publishes no set thresholds.** The popular "10–20 sets/week" number is interpretation, not a finding — never present it as one.
- **Proximity to failure drives hypertrophy, not strength.** [Refalo et al. 2024](https://sportrxiv.org/index.php/server/preprint/view/295). Hypertrophy slopes negative with CIs excluding zero; strength CIs contained the null. Authors flag it as exploratory.
- **No magic rep range.** [Schoenfeld et al. 2021, *Sports*](https://www.mdpi.com/2075-4663/9/2/32) — similar growth across loads ≥ ~30% 1RM, provided sets approach failure. This is what licenses choosing rep ranges to fit *equipment* rather than dogma.
- **Load progression and rep progression both work.** [Plotkin et al. 2022, *PeerJ*](https://peerj.com/articles/14142/). Justifies double progression.
- **Load control is the dominant injury mechanism.** [Kerr et al. 2010, *AJSM*](https://journals.sagepub.com/doi/10.1177/0363546509351560) — 65.5% of weight-training ED presentations were weights dropping on or striking the person; 90.4% free weights.

**Tier 2 — real but small or mixed**

- Longer rest mildly better, plateaus ~90 s ([Frontiers 2024](https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2024.1429789/full)); CIs cross zero.
- Frequency effects on hypertrophy negligible at equated volume (Pelland et al.).
- **Autoregulation is NOT proven superior to percentage-based programming.** [Hickmott et al. 2022, *Sports Medicine – Open*](https://sportsmedicine-open.springeropen.com/articles/10.1186/s40798-021-00404-9) — MD 2.07 kg, 95% CI −0.32 to 4.46, n.s. The engine's justification is practical (adapts to bad sleep, needs no 1RM test), **not** that it grows more muscle. The app must not claim otherwise.
- **RIR estimates are unreliable far from failure.** [Remmert et al. 2023](https://journals.sagepub.com/doi/10.1177/00315125231169868) — accuracy improves near failure; training experience did *not* help. Hence `RIR_TRUST_CAP = 3`.
- Set-to-set drop-off for sets **to failure**: ~70% / 55% / 50% / 45% of set 1 ([Stronger by Science](https://www.strongerbyscience.com/reps-sets/), secondary source summarising 29 studies). Used **only** as an anomaly band, never as a prescription.

**Tier 3 — practitioner framework, no published validation**

- MEV/MAV/MRV volume landmarks (Renaissance Periodization). Show set counts; **do not draw threshold lines**.
- Scheduled calendar deloads. [Coleman et al. 2024, *PeerJ*](https://peerj.com/articles/16777/) found a 1-week deload gave no hypertrophy benefit and *worse* strength gains.

---

## Do NOT do these things

A fresh agent will be tempted toward every one of these because they are what fitness
apps conventionally do. Each was rejected deliberately.

1. **No calendar deloads.** Stall-triggered only, and always *suggested*, never auto-applied. Contradicted by Coleman et al.
2. **No MEV/MRV threshold lines** on volume charts. Unvalidated. Counts only.
3. **No hard-coded 8–12 rep range.** Ranges are per-exercise and chosen to absorb the equipment's load increment. Fixed-weight bars get 8–15 because a 10 lb jump on a 50 lb bar is 20%.
4. **Do not trust RIR ≥ 4.** Cap it at 3 for all calculations and move by reps rather than load when it is high.
5. **Do not cut the load when later sets fall short.** That is a fatigue/recovery signal. Only a **set 1** miss is a strength signal. Conflating these is the standard failure of existing apps.
6. **Do not re-round weights onto an absolute grid.** See bug 3 below.
7. **Do not claim autoregulation is scientifically superior** to a fixed plan.
8. **Do not add frequency nagging.** Negligible for hypertrophy at equated volume.
9. **Do not build a program builder or mesocycle planner in v1.**
10. **Do not remove `target_weight` / `target_reps` / `target_rir` from `SetLog`.** Storing the prescription alongside the result is what makes an engine possible at all. Most logging apps store only the result, which is why they can never build one.

---

## Current state

**Done:** research pass, spec, Python reference engine, exercise library, 36 tests.

**Not started:** storage layer, PWA, UI, hosting.

```
CLAUDE.md            this file
README.md            how to run; owner-facing
docs/spec.md         data model + algorithm, rev 2
docs/evidence-base.md  every citation, tiered by strength
pytest.ini           puts project root on sys.path — do not delete
engine/
  models.py          dataclasses
  safety.py          RIR floor for solo training
  progression.py     the decision logic — this is the product
  library.py         equipment presets, fractional volume counting
tests/test_engine.py 36 tests; names are the behaviour contract
sim.py               multi-session walkthrough — read this first
```

Run: `pip install -r requirements.txt && pytest && python sim.py`

### Engine summary

- **Prescription:** per-set, with an **RIR ramp** — set 1 → RIR 2, middle → 1, last → 0. Rationale: taking set 1 to failure costs ~30% of set 2 and ~45% of set 3, and volume is the Tier 1 driver, so buying failure early is plausibly a net loss.
- **Safety floor** resolution order: safe-to-failure exercise → rack safeties → spotter → floor of 1. **Rack safeties rank above a spotter deliberately** — pins solve it permanently; a spotter is a variable the lifter does not control.
- **`stopped_at_cap`** disambiguates a capped RIR 1 ("I had more, was told to stop" → progress) from a true RIR 1 ("that was everything" → hold). Same logged value, opposite correct action.
- **Progression:** double progression — reps to the top of range, then load, reset reps.
- **Diagnoses:** `PROGRESS_REPS`, `PROGRESS_LOAD`, `HOLD_CONSOLIDATE`, `REPEAT_TOO_HEAVY`, `REPEAT_FATIGUE`, `STALL_INTERVENTION`, `FIRST_TIME`.

### Known v1 limitation

Rep targets are **flat across sets**. A lifter near their ceiling therefore oscillates,
progressing roughly every third session instead of smoothly. Fitted per-set decay is
the v1.1 fix and **must be regressed against the owner's own logged data** — the
literature priors describe sets to failure and would be wrong here. This is why v1
logs per-set targets against per-set actuals.

---

## Five bugs already found — do not reintroduce

All five were found by **running realistic multi-session scenarios**, not by unit
tests. Four of the five passed a green test suite.

1. **Capped-RIR misread.** A cap-limited RIR 1 read as a true effort ceiling would have stalled every barbell lift forever. Guard: `test_capped_set_one_is_not_read_as_true_failure`.
2. **Fatigue deadlock.** Set 1 hitting while set 3 faded held the prescription identical *forever*. Fixed with `FATIGUE_PATIENCE = 2`, after which the engine progresses on set 1's merit. Guard: `test_persistent_fatigue_does_not_deadlock_the_lifter`.
3. **Off-grid load rounding.** `135 + 10` was re-rounded onto a 10 lb grid and became **140**, silently losing 5 lb every cycle. Real gym weights are rarely multiples of the increment because the bar is 45. Never re-round onto an absolute grid; add the increment to the current weight. Guard: `test_load_progression_adds_the_full_increment_from_an_off_grid_weight`.
4. **Self-contradicting note** printed "moving by reps" on load-progression decisions.
5. **Floating point in deload constants.** `1 - 0.9 == 0.09999999999999998`, which floored to the wrong step and deloaded 100 lb to 92.5. Store drops as `0.10`, never as `1 - 0.90`.

**Process lesson worth keeping:** unit tests verify the code does what was intended;
`sim.py` reveals whether the *intent* was right. Add a scenario to `sim.py` for any
new behaviour, and read the output.

---

## Open questions — ask, do not assume

1. **Pull day and leg day exercises.** Blocking. Run fractional volume counting on both before writing UI.
2. **Does the gym have a power rack with adjustable safety pins?** Never confirmed. Determines whether the safety floor ever binds. (It does *not* bind anywhere on his current push day — Smith racks anywhere, dumbbells can be dumped, standing press goes forward, cables are harmless.)
3. ~~Cable stack increment~~ — confirmed: all cable machines at this gym are 5 lb steps. Set as the `cable` preset default in `library.py`, so every cable exercise inherits it automatically.
4. **Dumbbell increment** — assumed 5 lb per dumbbell.

### Finding already surfaced, not yet acted on

Fractional counting on his push day, 3 sets each:

| Muscle | Sets |
|---|---|
| Triceps | 10.5 |
| Front delts | 9.0 |
| Chest | 6.0 |
| Side delts | 1.5 |

**Chest is the least-trained muscle on his push day.** Note the framing carefully:
because Pelland et al. publish no thresholds, the defensible claim is that the
*relative allocation is inverted for the day's stated purpose* — not that 6 sets is
objectively too few. Suggested fixes: add a third chest movement; add lateral raises
for the side delts. Not yet decided by the owner.

---

## Next steps

1. Get pull + legs; run volume counting on both.
2. Port the engine to JavaScript. **Build a parity harness** — run identical scenarios through Python and JS and diff the outputs. A hand port will drift.
3. Storage layer: IndexedDB, offline-first, **automatic JSON export from day one** (browser storage can be evicted; this also makes any future platform migration cheap).
4. Logging screen only. Big touch targets, one-handed, minimum taps per set, rest timer.
5. Host on GitHub Pages (owner's choice). HTTPS is required for service workers — a local `file://` copy will not install as a PWA or work offline.
6. Owner trains with it for three weeks, **adds no features**, keeps a friction log. That log is the v1.1 spec.

Testing available in the sandbox: Chromium and Playwright are pre-installed. Drive
the PWA at Galaxy viewport (412×915), screenshot each state, verify interactions
before the owner ever sees it.

---

## Working style the owner has asked for

- Cite the specific publication and URL inline. Distinguish sourced rules from reasoning.
- **Push back.** Do not be agreeable when there is a better option. Every significant improvement in this project so far came from disagreeing with the initial framing — moving the safety layer from v1.2 into v1, refusing to hard-code fatigue constants, catching that the volume allocation was inverted.
- Success matters more than comfort.
