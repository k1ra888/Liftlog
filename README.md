# Progression engine

The decision logic for the training app, with no UI and no storage attached. This
exists so the logic can be argued with and verified before anything expensive is
built on top of it.

Everything here traces to `spec.md` and `evidence-base.md` in the project.

---

## Running it

You need Python 3.11 or newer. Nothing else.

```bash
pip install -r requirements.txt

pytest            # 33 tests — the behaviour contract
python sim.py     # 12-session walkthrough, human-readable
```

`pytest.ini` puts the project root on the path, so both commands work from the
project folder with no environment setup.

### In PyCharm

1. **File → Open**, select this folder (the one containing `pytest.ini`).
2. When prompted for an interpreter, pick any Python 3.11+. If PyCharm offers to
   download one, let it.
3. Open the terminal at the bottom and run `pip install -r requirements.txt`.
4. Right-click `tests/test_engine.py` → **Run 'pytest in test_engine.py'**.
5. Right-click `sim.py` → **Run 'sim'**.

If step 4 reports `ModuleNotFoundError: No module named 'engine'`, PyCharm has
overridden the working directory. Fix: **Run → Edit Configurations → Working
directory** → set it to this folder.

---

## What to actually look at

Reading test output tells you the code does what I said it does. That is the less
interesting question. The interesting one is whether the engine's *decisions* match
what you would want a coach to tell you.

**Start with `sim.py`.** It simulates a lifter with a real strength ceiling and
within-session fatigue, then prints every prescription and the reasoning behind it.
Twelve sessions, about a page. If any decision looks wrong to you, that is worth
raising — it is far cheaper to change now than after there is an interface on top.

**Then set one breakpoint.** `engine/progression.py`, in `progress()`, on the line
`outcome = classify(ws)`. Run `sim.py` in debug mode and step through. That function
is the entire product; everything else is plumbing.

---

## Layout

```
engine/
  models.py       dataclasses — Exercise, SetLog, ExerciseState, Decision
  safety.py       RIR floor for training alone (spec §3)
  progression.py  the decision logic (spec §2, §4)
  library.py      equipment presets + fractional volume counting
tests/
  test_engine.py  33 tests; read the names, they are the spec in miniature
sim.py            readable multi-session walkthrough
```

## The two bugs worth knowing about

Both are documented in the tests, and both are the kind that would have been
painful to find later.

1. **Capped RIR vs true RIR.** When training alone caps a set at RIR 1, that reading
   means "I had more and was told to stop" — the opposite of an uncapped RIR 1,
   which means "that was everything." Same logged number, opposite correct action.
   `stopped_at_cap` disambiguates them. See
   `test_capped_set_one_is_not_read_as_true_failure`.

2. **The fatigue deadlock.** A lifter whose set 1 keeps hitting while set 3 fades
   was held at an identical prescription forever. Every unit test passed; only the
   multi-session simulation exposed it. See
   `test_persistent_fatigue_does_not_deadlock_the_lifter`.

The second one is the argument for running `sim.py` rather than trusting a green
test run.

## Known v1 limitation

Rep targets are flat across sets, so a lifter near their ceiling oscillates —
progressing roughly every third session instead of smoothly. Fitted per-set decay
(v1.1) is the fix, and it needs real logged history to calibrate against.

## Note on language

This is the reference implementation. The app itself will be JavaScript, so this
Python gets ported once the logic is settled. It is the specification, not the
shipping code.
