> **Superseded on 2026-11-24. See `phase2/new/DAY3-CHECKLIST.md`.** This list predates the 24-Nov findings (one phone, accelerometer at stops, a Wi-Fi logger that saves every scan). Kept for history only.

# What's left to collect

Status after the **23 Nov** two-floor session (42 stops, both floors, gyro + dense Wi-Fi).

## ✅ Already collected — don't redo
- Floor 5 **and** floor 4 loop (42 stops), incl. **inner-hallway rooms and stairs**, lifts, LTs, escalators.
- **Gyroscope + magnetometer during the walks** (heading data).
- **Dense Wi-Fi** — 41/42 stops covered (~39 scans each). The 60 s dwell beat the throttle.
- **Floor-5 coordinates** (Google-Maps pins).

## 🔲 Still needed
1. **Floor-4 coordinates** — drop Google-Maps pins like floor 5 for: Y4 / Y4502, LT 1A, 1B, 2A, 2B, exit gate (`pintu keluar`), the floor-4 exits/lifts/stairs, and the **escalator bottom landing**. Send me the lat/long list — I compute all distances.
2. **One more fingerprint day** — walk the **same checkpoints** again on a **different day and time** (e.g. a busy vs quiet hour). This is what lets us *train on days 1–2*. Same phones, same settings.
3. **A separate test-walk day** — on yet another day, record **one continuous walk** and tap the **"I'm here" button** at each checkpoint. Those timestamps are the **ground truth** we score against (*test on day 3*). Include a couple of **deliberate wrong turns** and a floor change.

## 🔧 Optional tidy-ups
- **BM23** (`exit 5 stairs`) got **no Wi-Fi** — re-record if you pass it again.
- **BM42** label is `(final stop – confirm)` — set it to Exit 5 (4F) in `clean-data/2026-11-23/locations_provisional.csv`.

## 📋 Collection habits for the next sessions
- **Stop → start New recording at each stop** (no pause/resume — it created duplicate files this time).
- Keep WiGLE on **Nonstop** (all three), dwell **~60 s** per stop, screen on, foreground.
- Walk recordings log **Accelerometer + Gyroscope + Magnetometer** together.
- Phone **flat, facing the object/landmark** at each stop; **flat, facing the way you walk** during movements.
- Photograph all three phone clocks at the start (for clock sync).

## Why the extra days?
You can't **train and test on the same day** — adjacent readings from one visit are nearly identical, so the score would be fake-high (leakage). A real accuracy number needs a **different day** as the test set. That's the single thing standing between "data collected" and "results we can report."
