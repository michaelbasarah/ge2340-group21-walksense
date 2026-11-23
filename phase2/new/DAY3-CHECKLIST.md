# Day 3 collection checklist

*Internal team notes, not report text (course rule: an LLM may only polish our own writing).*

Target: collect by **Thu 26 Nov** (deadline 30 Nov). Why we change the method: see `TEAM-SUMMARY-2026-11-24.md` (section c). This replaces `../old/WHATS-LEFT-TO-COLLECT.md`.

## Before you leave

- [ ] **Pick ONE phone and use it for everything**: stops and walks, today and on every later day. Write down which phone it is. (The two iPhones' magnetometers disagree, r = 0.20, so their data can't be mixed.)
- [ ] **Accelerometer + gyroscope + magnetometer + barometer ON for stop recordings too**, not only for walks. (With the accelerometer we can correct for how the phone is tilted. On walk data this was the only feature set that recognised places: 39% vs 0%.)
- [ ] **Use a Wi-Fi logger that saves EVERY scan.** The WiGLE CSV only logs an access point when it is new or stronger, so repeat scans are lost. First test WiGLE's database export (or a scan-logging app) at one spot: the same access point must show up at the stops next to it.
- [ ] Android: Developer options -> **Wi-Fi scan throttling OFF**. Screen on, app in the foreground. If you use WiGLE, set it to Nonstop.
- [ ] **Photograph all phone clocks** (every phone you use) at the start, for clock sync.

## At every stop

- [ ] **Start a NEW recording at each stop.** No pause/resume (it made duplicate files before).
- [ ] **Stay about 60 s.** (30 s stops hurt the 17-Nov data.)
- [ ] **Hold the phone flat, facing the landmark**, the same way every time.
- [ ] **Name the place exactly as in `cross-day/labels_23nov_confirmed.csv`.** The 31 names:
  - Floor 5: `canteen`, `exit_5`, `male_toilet`, `y5302`, `y5302_back`, `sr11`, `sr10`, `sr9`, `sr8`, `y5202`, `female_toilet`, `exit_10`, `escalator_up`, `escalator_down`, `disabled_toilet`, `lift_5`, `exit_5_stairs`, `y5401`
  - Floor 4: `exit_5_stairs_4F`, `lift_5_4F`, `disabled_toilet_4F`, `exit_5_4F`, `lt2a`, `lt2b`, `escalator_down_4F`, `y4502`, `escalator_up_4F`, `lt1b`, `lt1a`, `exit_10_4F`, `entrance_exit`
- [ ] **Always a stop, then a walk**, then the next stop. A stop with no walk after it can't be named automatically. Don't skip walks.

## During walks

- [ ] Same phone as the stops. Log accelerometer + gyroscope + magnetometer together.
- [ ] Phone flat, facing the way you walk.

## Separate test walk (on another day, not the same day as the fingerprint stops)

- [ ] Record **one continuous walk** and tap **"I'm here"** at each checkpoint. These timestamps are the ground truth we score against.
- [ ] Include **a couple of deliberate wrong turns** and **a floor change**.

## Extra data

- [ ] **Floor-4 Google Maps pins** (like floor 5) for: Y4 / Y4502, LT 1A, 1B, 2A, 2B, the entrance/exit gate, the floor-4 exits, lifts, stairs, and the bottom of the escalators. Send the lat/long list.
- [ ] Optional: BM23 (`exit_5_stairs`) had no Wi-Fi on 23 Nov. Re-record it if you pass it.

## Why we need other days

Training and testing on the same day gives fake-high scores (leakage): neighbouring readings from one visit are almost identical. A real accuracy number needs a different day as the test set.
