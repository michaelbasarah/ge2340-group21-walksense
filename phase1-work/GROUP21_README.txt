GE2340 GROUP 21 - PHASE 1 NOTES
===============================

DEADLINE: Monday 19 Oct 2026, 23:59 HKT. No late submissions (late = 0).
Submit ONE zip on Canvas (Phase 1 assignment) containing:
  1. Proposal PDF (max 2 pages including references)
  2. Contribution statement PDF, signed by ALL four of us
Only ONE person submits. Canvas only grades the latest submission from the group.


WHAT WE NEED FROM EACH OF YOU (ASAP, before tonight)
----------------------------------------------------
Chris, Benedicta and Michael, please send:
  - Your student ID (SID)
  - Your CityU email (email-withheld)
Everyone (including Emmanuelle):
  - Your contribution percentage (all four must add up to 100%)
  - 1-2 lines on what you actually did (be specific; "helped with the
    project" is not allowed by the template)
  - Your signature and the date on the contribution statement
    (print, sign and scan, or sign the PDF digitally)


OUR PROJECT
-----------
Name:  WalkSense: Camera-Free Indoor Navigation at CityU

Problem:
  Students (especially new and exchange students) get lost inside CityU's
  academic buildings (AC1, AC2, AC3, Yeung Kin Man). GPS does not work
  indoors and cannot tell floors apart. The CityUHK Mobile app only gives
  directions to the building, not to the room.

How it works:
  1. The user types where they are and where they want to go, like Google
     Maps (e.g. "AC1 lift lobby 3/F" to "LT-5").
  2. A* search plans the route over a map graph of corridors, lifts and
     stairs that we build by hand.
  3. While the user walks, the phone tracks them using its sensors:
     step counter, compass, Wi-Fi signal strength, Bluetooth beacon signal
     strength, magnetometer (magnetic field) and barometer (floor changes).
  4. It warns the user if they take a wrong turn.
  5. EXTRA feature: instead of a room, the user can choose "nearest free
     study spot". A model predicts how busy each study spot is from the
     time, week and class timetable.
  No cameras, no photos, no audio.

Scope: 2-3 floors of AC1 and AC2. NOT the Library, NOT outdoor routes.


THE AI PART (what to say if asked "where is the AI?")
-----------------------------------------------------
  - Supervised classification: a model (k-nearest neighbours or random
    forest) learns which checkpoint you are at from the sensor readings.
  - Probabilistic tracking: a hidden Markov model (HMM) combines all the
    signals over time, keeps you on the route and detects wrong turns.
  - Search: A* finds the shortest route on the map graph.
  - Regression: predicts how busy each study spot will be (extra feature).

The five tracking methods we compare:
  A. Steps + compass (dead reckoning): no setup needed, but drifts over
     distance.
  B. Wi-Fi fingerprinting: uses existing campus Wi-Fi, but Android only
     (iPhones don't let apps scan Wi-Fi).
  C. Magnetic fingerprinting: the steel in the building distorts the
     magnetic field in a unique way at each spot. Works on any phone.
  D. Bluetooth (BLE) fingerprinting: a few cheap beacons placed along the
     route. Works on iPhone too. Needs permission to place the beacons.
  E. HMM fusion of everything + barometer: expected to be the best.
     Fixes drift and detects floor changes.

We also compare A* routing with just asking an LLM for directions (the
LLM can make up corridors that don't exist, so A* is better).


TRAINING DATA (if the professor asks)
-------------------------------------
Short answer: "We make our own dataset. No public dataset exists for
CityU's buildings, so we collect and label it ourselves."

How:
  1. Mark about 80 checkpoints along the corridors, every 3-5 m, on 2-3
     floors. Each gets an ID like AC1-3F-C12. That ID is the LABEL.
  2. Stand at each checkpoint for about 30 seconds while the phone records:
       - Wi-Fi signal strengths (WiGLE app, Android only)
       - Bluetooth beacon signal strengths
       - magnetic field + barometer (phyphox app, free)
     Each recording is saved with its checkpoint ID = labelled data.
  3. Repeat on different days, at busy and quiet times, with different
     phones and different group members.
     Roughly 80 checkpoints x 4 visits x ~10 scans = ~3,000 labelled samples.
     (Signals change with crowds, so the model has to learn to handle that.)
  4. Testing: on a SEPARATE day, walk real routes and tap a button each
     time you pass a checkpoint. Those taps are the ground truth.
     We never test on the same day's data we trained on.
  5. Study-spot extra: count occupied seats at 15-20 study spots a few
     times a day for about 4 weeks, plus the public class timetable.
     Label = percentage of seats taken.

Likely follow-up questions:
  Q: Is 3,000 samples enough?
  A: Yes. kNN and random forests work well on small data. That's why we
     don't use deep learning.
  Q: What about privacy?
  A: We only record campus Wi-Fi router IDs and signal strengths. No
     personal data, no photos, no audio.
  Q: Any public dataset?
  A: We can also test on UJIIndoorLoc, a public Wi-Fi fingerprint dataset
     from a university campus in Spain (Torres-Sospedra et al., 2014).

How we measure results:
  - % of checkpoints and floors identified correctly
  - Position error in metres
  - How far someone walks before a wrong turn is detected


SIX-WEEK PLAN (Phase 2, due 30 Nov 2026)
----------------------------------------
  Week 1: Build the map graph (corridors, lifts, stairs)
  Week 2: Record fingerprints at checkpoints, place test beacons
  Week 3: Record test walks (with lift rides and deliberate wrong turns)
  Week 4: Train and compare methods A to E in Python
  Week 5: Test with first-year students
  Week 6: Write report + record the 12-15 min video (everyone shows face
          and speaks)

Tools: our own Android + iPhone phones, phyphox and WiGLE (free apps),
Python.

Risks and how we handle them:
  - Corridors that look alike: we combine several signals (fusion).
  - iPhones can't scan Wi-Fi: magnetic + Bluetooth still work on iPhone.
  - Permission to place beacons: we ask the building office first.


PRIOR CITYU WORK (why ours is different)
----------------------------------------
  - CityUHK Mobile app: directions only to the building.
  - 2013 CityU student prototype: Wi-Fi, room-level only, Android only,
    never deployed.
  - LibCompass (2018): Bluetooth beacons, but only inside the Library.
  Ours: no cameras, follows you along the whole route (not just "which
  room"), works on both Android and iPhone.


FILES (in Emmanuelle's GE2340\Phase1 folder)
--------------------------------------------
  Phase1_Proposal_humanized.tex   - proposal source (LaTeX)
  Phase1_Proposal_navigation.pdf  - current proposal PDF (2 pages)
  Phase1_Contribution.tex / .pdf  - contribution statement (to fill + sign)
