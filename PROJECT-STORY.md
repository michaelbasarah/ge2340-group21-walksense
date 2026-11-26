# WalkSense: the project story (GE2340 Group 21)

> **Internal team notes, not report text.** Course rule: an LLM may only polish our own writing, so nothing here is meant to be pasted into the report. Every number below is copied from `PROCESS-LOG.md` (entry numbers in brackets, e.g. [32]), which names the output file it came from. If you need a number for the report, go to the entry and its file, not to this page.

Written 26 Nov 2026. Times are Hong Kong time. Entries 77 and 78 are reserved for two branches still running when this was written (A56 offset, route planner); 77 (A56 offset) is now written on branch `feat/a56-offset`.

---

## 1. The problem and the idea (Phase 1)

CityU's academic buildings are a maze of wings, floors and links, and GPS does not work indoors or tell floors apart. The Phase 1 proposal (`phase1-work/Phase1_Proposal_v2.tex`) set out **WalkSense**: type where you want to go, and the phone tells you where you are and how to get there, using only sensors every phone already has.

Three AI pieces were proposed:

| Piece | Proposed methods | Where it ended up |
|---|---|---|
| Understand the request | keyword rules, sentence embeddings, or an LLM that may only answer a real place ID | LLM (Gemini) with a keyword -> fuzzy offline fallback [59, 64, 71, 75, 84] |
| Plan the route | A* on our corridor graph vs an LLM given a text floor plan | A* (always valid, matches Dijkstra) [52-55] |
| Know where the user is | (A) step counting, (B) Wi-Fi fingerprint, (C) magnetic fingerprint, (D) a tracker fusing them with the barometer for the floor | magnetic kNN at stops + barometer floor + corridor tracker; Wi-Fi failed [11-15, 20, 30-32] |

The scope shrank to AC1 floors 5 and 4 (26 places in the final place list, graph-v2 [22]). The proposal's user tests were dropped by the user on 25 Nov [83].

---

## 2. Collection days at a glance

| Day | Who / phones | What we got | What went wrong | Entries |
|---|---|---|---|---|
| **14 Nov** | three phones: one iPhone for barometer + magnetometer, another for the accelerometer, a Samsung for Wi-Fi | 26 stops, 23 walks, 1 Wi-Fi log | the location list was judged unreliable, so every label became "untrusted"; 26 stop files vs 25 descriptions, never explained | [1, 2] |
| **17 Nov** | stops on iPhone17,4, walks on iPhone19,2, Wi-Fi on the A55 (WiGLE) | 26 stops at about 30 s, 23 walks, walk files named by route | Wi-Fi covered only 15 of 26 stops (Android scan throttling); one stop exported twice | [4] |
| **23 Nov** | one collector, two floors, gyroscope added | 42 stops (about 60 s), 37 walks, 2 Wi-Fi logs | pause/resume made duplicate recordings; the label rule "stop = origin of next walk" mislabelled stops with no walk after them (6 of 42 changed after the collector's route list) | [7, 9] |
| **24 Nov s1 / s2** | s1: ip18 (iPhone19,2), S24, A55, A56 + Wi-Fi; s2: ip16 (iPhone17,4), S24 | s1 220 recordings (27 stops, 28 walks), s2 108 (26 stops, 28 walks); phone facing the door at every stop | the "iphone" was two different handsets (READMEs called both "16 Pro"); weather moved pressure 0.833 hPa over a long break; the S24 barometer is unusable for floors; WiGLE again logs only new-or-stronger networks | [23, 30, 31, 37] |
| **25 Nov afternoon** | Dicta: full pass with ip18, A55, A56; Tian (ip16) and Michael (S24): spot takes at the hard places | Dicta's complete set: 161 recordings, 26 stops + 28 walks, Wi-Fi at 26/26 stops; 11 S24 + 4 ip16 spot takes | only the iPhone logged pressure; the laptop's WhatsApp export missed 73 files; WhatsApp stripped the S24 file names, and 3 labels guessed from timing were all wrong | [28, 42, 49, 69, 79] |
| **25 Nov night** (21:40 to 00:40) | Dicta ip18 and Chris A56 in step, Tian ip16 on his own; then extra takes at the weak places | 169 recordings + 1 WiGLE log; ip18 and A56 32 stops each (24 loop + 8 extra), ip16 23 stops | Chris's A56 magnetometer read a median 110.9 uT all night (40 to 45 uT on other days); Dicta's iPhone logged no pressure in 27 of 59 takes; three re-exports from the laptop held none of it; Chris's 8 extras were first missed in the manual download | [72, 79, 87] |
| **26 Nov morning** | Tian, ip16 | 52 recordings (25 stops + 27 walks), all with a barometer | his phone saved 51 files as "point <time>", so labels came from his chat captions, matched strictly in order | [73] |

---

## 3. The big turns

### 3.1 The 94% that was not real (17 to 24 Nov) [5, 8-10]
Dicta's first pilot on the 17-Nov data gave **94.2%** stop accuracy with kNN. Train and test slices came from the same recording, so neighbouring 2 s slices were near-copies: leakage. The first honest tests on 24 Nov: **7/9 = 78%** on 23-Nov revisits and **18 to 24%** across days (train 23 Nov, test 17 Nov). The pilot moved to `phase2/old/` and is never quoted as a result.

### 3.2 The 24-Nov failures that wrote the collection rules [11-15, 17]
Four failures in one day: a fixed pressure threshold breaks with the weather [11]; WiGLE rows are not repeated scans, so Wi-Fi is near useless [12]; no accelerometer at stops, so no tilt correction [13]; two iPhones' magnetometers disagree (r = 0.20) [14]. Tilt helped only on 23-Nov walk endpoints (39% vs 0%) [15] and not across days later [30]. These became `phase2/new/DAY3-CHECKLIST.md`: one phone per protocol, log everything at stops, phone flat facing the door, new recording per stop.

### 3.3 Maps, graph and tracker (24 Nov) [18-22, 33]
Areas pre-registered before testing [18], 39 graph edges from the walks plus step counting [19], an HMM tracker on the graph [20] (v1 never recovered from one wrong stop, so it needed a small "could be anywhere" share), a circle-navigator UI [21] and graph-v2 with merged study rooms and lift/stairs [22]. Lesson: a map cannot replace a fingerprint; it helps when every place already has one.

### 3.4 Tian's upload app and the first fair test (25 Nov) [24-27, 66]
A phyphox ZIP is uploaded from the phone to the laptop, which answers with floor, steps and top-3 places. Trained on one 24-Nov session and tested on the other: **17/26 and 17/27** across two different iPhones, floor **27/27 and 26/26** after the floor rule changed from "previous reading" to "median of the last 6". Raw x/y/z won over tilt because the phone was held the same way at every stop. Live mode reads phyphox remote access while walking [26, 27]; it first connected to a real phone on 25 Nov, but no live walk has been scored yet [86].

**ip16 vs ip18 for the demo (26 Nov, [89]).** The demo will use Dicta's iPhone 18, so the user asked whether Tian's iPhone 16 data can be pooled. Tested on the three ip18 sessions (85 stops): trained on ip16 alone the app model gets 57/85 against 65/85 for ip18 only, so the phones are not interchangeable; adding ip16 to ip18 training gives 67/85 in the app model and 58/85 against 59/85 in the day-3 fused kNN, a tie. Recommendation: ip18 only.

### 3.5 One fused kNN, scored honestly (25 Nov) [32]
The user's design: one weighted kNN over all phones and sessions, with a learned weight per sensor group. Scored four ways on purpose: random windows **99.7%** (leaky) -> by recording 55.4% -> grouped by stop **28.7%** -> leave one session out **74/202 = 36.6%** (chance 3.8%). Wi-Fi and the floor belong to the stop, not the phone, which was a leak we had not named before.

### 3.6 split20 (25 Nov) [40]
The user's data notes: cut each 60 s take into three 20 s pieces, drop the 23-Nov stairs and sr8/sr10/sr11, remove obvious outliers. Leave one session out went 36.6% -> **38.5%**, but a control showed the gain came from removing hard test pieces, not from a better model. Pieces of one take are not independent. Both variants are kept; the team still has to pick which one the report quotes.

### 3.7 The 25-Nov data, the hard places and the phone ranking [41-51]
The never-correct places were named *before* the new data went in [41]. The partial export lifted the total to 40.4% [44]; Dicta's complete pass lifted it to **123/287 = 42.9%** (split20 **385/818 = 47.1%**) and left **no place at zero correct** [50]. Phone ranking then: ip18 0.698, ip16 0.500, A56 0.453, S24 0.250, A55 0.226 [50]. The per-phone sheet keeps dated tabs and an append-only Progress tab [45]; the data-gaps sheet uses rules fixed before looking [51].

### 3.8 Routing, request matching, smoothing, results pack (25 Nov) [52-65]
- **Routing:** A* matched Dijkstra on all 650 pairs (after a first admissibility check failed on rounding) [53]. An LLM given the corridor list with distances invented 0 hops of 203; with only a place list it invented 59 of 93 [55].
- **Request matching:** the committed starter result (23/23) re-ran as 18/23 [56]. On the 62-query test split: keyword 44/62, embeddings 44/62, LLM **60/62** [59]; hybrid keyword -> fuzzy -> LLM 56/62, with all misses wrong local matches [64].
- **Smoothing** (the user's a·p_t + b·p_t-1 + ... idea): no accuracy gain, because the wrong answers at a stop are steady, not jumpy; gating on stillness is what stops the jumps while walking; a per-phone offset made things worse [60, 61].
- **Results pack:** every quoted number generated from a file, with chance and n [62, 65, 67].

### 3.9 Labels from the people who stood there (26 Nov) [68, 69, 79]
36 duplicate ZIPs deleted only after SHA-256 was recomputed against all of Dicta's files [68]. Michael's 11 S24 files were renamed from his own chat names; the 3 timing guesses had all been wrong [69]. Total after: **122/295 = 41.4%**. The same near miss happened again with two 20:2x S24 takes, caught before any label was written [79].

### 3.10 The app grows: vector map, search, Gemini (26 Nov) [70, 71, 75, 84]
The sketch had been drawn over a Google indoor-map screenshot, which turned it into a survey: a metric floor plan for both floors, 0.75 m RMS against the Google pins [70]. Search: Gemini when a key is in `.env`, keyword -> fuzzy offline otherwise, A* route drawn on the plan [71]. Gemini scored **124/128** alone, hybrid 115/128 [75]. No RAG: all 26 places fit in the prompt [84].

### 3.11 The night run and Tian's morning (26 Nov) [72, 73]
The night run lifted ip18 to **60/85 = 70.6%** and gave ip16 its first same-handset test; the total became **169/386 = 43.8%**. Chris's A56 night takes scored 2/32 because of the magnetometer offset (kept, not dropped). Entry 77 compared keep / exclude / recalibrate: the offset drifted over the night, a label-free circle fit lifts those takes from 2/32 to 11/32 (16/32 with a time-local fit) but not to the A56's normal level (30/53); excluding them gives **190/379 = 50.1%** (split20 **526/1092 = 48.2%**); recommended: exclude for the headline numbers, team to decide [77]. The upload app's floor tracker got only 20/32 because Dicta's iPhone stopped logging pressure across the 5F -> 4F change. Tian's morning pass made ip16 a three-session handset (total **178/411 = 43.3%**, split20 **553/1183 = 46.7%**) and showed that his doubtful night "lt2b"/"lt2a" stops match LT1B/LT1A (3.0 and 14.2 uT) [73].

### 3.12 Floor rules (26 Nov) [74, 76]
Pre-registered, tuned on four sessions, scored on held-out ones. Rule (d), pressure first and the magnetic vote only when pressure is missing or after a long gap: **30/32** on the night dropout where the app got 20/32, with no loss elsewhere [74]. The user's idea of switching floor only after a lift/escalator landing failed as pre-registered: the place guess names the right connector too rarely to open the gate (37 of 101 connector stops for the day-3 kNN) [76]. Nothing was wired into the app; adopting (d) is a team decision.

### 3.13 The app adopts floor rule (d), drops the a56 night from training, and keeps disabled toilets free (27 Nov) [90]
The user adopted rule (d) for the app. Re-checked with the app's own 2 s windows it still passed the pre-registered iPhone rule: the app's night floor went from **20/32 to 30/32** with no stop lost elsewhere; for phones without a barometer the rule still did not pass, so they keep the pressure-only rule unless a switch is set. Chris's a56 night takes no longer train the app's a56 model (a56 xyz 13/27 and 14/26 on its other sessions). In Standard mode a toilet request now goes to an ordinary toilet whenever one fits; a disabled toilet only when none does (in our data: a "4F" request). The upload README was corrected for the demo (port 80, `--device iPhone19,2`, build step, WSL networking) [90].

### 3.14 A runbook for the demo and a scoring rule written before the first live walk (27 Nov) [92]
The demo phone is Dicta's iPhone 18 only [89]. `phase2/new/DEMO-RUNBOOK.md` collects the night-before checklist, the start commands, a 2-minute self-test, a failure table and the 8 weak places to retake. Checking the commands again found that the upload README still said port 8080 although the phone serves on port 80 (entry 86), and that a fresh clone still stops with `KeyError: 'mag'` until two build scripts are run [81]. `phase2/new/live-walk/PROTOCOL.md` fixes, before any live walk, a 7-stop route through the strong places, what counts as a correct lit place (10 s after arrival) and how to file the results.

---

## 4. Milestone numbers

Chance is 3.8% (26 places) unless noted. "LOSO" = leave one whole session out (honest).

| Date | Milestone | Number | Entry |
|---|---|---|---|
| 17-23 Nov | Pilot, same-recording split (**leaky**) | 94.2% | [5] |
| 24 Nov | 23-Nov revisits (chance 3.2%) | 7/9 = 78% | [10] |
| 24 Nov | Cross-day 23 -> 17 Nov (chance 6.7%) | 18 to 24% | [10] |
| 25 Nov | Upload app, iPhone -> other iPhone, 24 s1 <-> s2 | 17/26, 17/27; floor 27/27, 26/26 | [24] |
| 25 Nov | Same handset across days, 23 Nov -> 24 s2 | 13/26 | [30] |
| 25 Nov | Fused kNN: random windows (**leaky**) / LOSO | 99.7% / 74/202 = 36.6% | [32] |
| 25 Nov | split20 LOSO | 222/577 = 38.5% | [40] |
| 25 Nov | + complete 25 Nov, LOSO default / split20 | 123/287 = 42.9% / 385/818 = 47.1% | [50] |
| 25 Nov | Routing: A* vs Dijkstra | 650/650 pairs equal | [53] |
| 25 Nov | Request matching, test split: keyword / LLM / hybrid | 44/62 / 60/62 / 56/62 | [59, 64] |
| 25 Nov | Upload app, 3 sessions, ip18 same handset | 19/26, 18/27 | [66] |
| 26 Nov | After the S24 relabel, LOSO default | 122/295 = 41.4% | [69] |
| 26 Nov | Vector floor plan fit | 0.75 m RMS | [70] |
| 26 Nov | + night run, LOSO default; ip18 | 169/386 = 43.8%; 60/85 = 70.6% | [72] |
| 26 Nov | + Tian's morning, LOSO default / split20 | 178/411 = 43.3% / 553/1183 = 46.7% | [73] |
| 26 Nov | Floor rule (d) on the night dropout (app: 20/32) | 30/32 | [74] |
| 26 Nov | Gemini request matching, all 128 / hybrid | 124/128 / 115/128 | [75] |

---

## 5. Failures and what each one taught

| Failure | What it taught | Entry |
|---|---|---|
| 94% pilot was leakage | split by session or day, never by recording; show the leaky number only next to the honest one | [5, 32] |
| "stop = origin of next walk" labels | check how a label was made; ask the collector for the route | [9] |
| Fixed pressure threshold | compare consecutive readings or recent medians, and watch long pauses | [11, 24, 30] |
| WiGLE "Wi-Fi" | a log that covers a stop is not a fingerprint; count repeated scans | [12, 31] |
| No accelerometer at stops; two iPhones disagree | log everything at stops; one handset per protocol; check device IDs, not nicknames | [13, 14, 37] |
| Tracker v1 never recovered | a tracker needs a way back | [20] |
| More 20 s pieces did not mean more evidence | run a control on the same test pieces before calling cleaning an improvement | [40] |
| Log numbers collided | number entries only when they land; provisional numbers on branches | [39, 48, 63, 82] |
| NaN floor threshold from one S24 stop | nan-safe statistics; diff old numbers after adding data | [44] |
| Partial WhatsApp exports | an export only holds what that device downloaded; each person exports their own, or pushes to GitHub; inventory manual downloads | [42, 79] |
| Labels guessed from timing | a label needs the name from the person who stood there | [69, 79] |
| Committed request-matching result was stale | re-run committed results before building on them | [56] |
| Keyword "eat" matched "theatre" | whole-word matching; local rules fail on typos | [58] |
| Smoothing did not raise accuracy; per-phone offset made it worse | smoothing fixes jitter, not bias; gate on stillness instead | [61] |
| A56 night magnetometer offset | check each phone's median field at ingest | [72] |
| Floor tracker with missing pressure | pre-register a fallback and test it where the main signal is complete too | [72, 74] |
| Connector-gated floor change | a gate is only as good as the place guess that opens it | [76] |
| App crash after landing data (`KeyError: 'mag'`) | gitignored derived data does not travel with a merge; rebuild in the target tree | [81] |
| Worker runs stopped (HTTP 429 / 403) | commit WIP steps; a 403 is the network, a 429 is wait-and-resume | [80] |
| Gemini timeout at 8 s on one call | pace free-tier calls and allow a longer timeout for evaluation | [75] |

---

## 6. Decisions and who made them

- **User (Michael):** split20 notes [40]; no production app, max 5 agents, no user tests [83, 85]; LLM search, Gemini free tier, offline fallback, no RAG [84]; plain Excel with append-only progress [45, 85]; push everything to GitHub [85]; trust the collectors' own names [69]; delete duplicates only after a byte check [68]; route planner, step-free mode, toilet gender filter, landing-gated floor change [76, 88]; save the story, not just the code [88]; floor rule (d) in the app, the a56 night out of the app's training, ordinary toilets first in Standard mode [90].
- **Team / collectors:** the route list that fixed the 23-Nov labels [9]; Dicta's complete 25-Nov push [28]; the name mappings confirmed on 26 Nov [69]. Still waiting: Tian's LT1/LT2 confirmation [73], Chris's phone set-up on the night run [72, 87], Dicta's phyphox barometer setting [72, 87].
- **Pre-registered before results (so nobody could tune to a wanted answer):** graph areas [18], never-correct places [41], data-gaps thresholds [51], smoothing selection rule [60], request-matching dev/test split [57], floor rules [74, 76].

---

## 7. What is still open (short list; the full list is at the end of `PROCESS-LOG.md`)

1. **Which numbers the report quotes:** take level or split20 [40]; which chance level and place list [62].
2. **A56 night takes:** keep, exclude or recalibrate. Entry 77: recommended exclude (B) for the headline numbers and the one-offset correction (C1: default **194/411**, split20 **614/1183**) as the evidence that the fault is a drifting hard-iron offset; do not correct phones without a fault. A full A56 redo only after a side-by-side |B| check against the ip18; no ip18 floor-5 redo needed for the fingerprints. `config.json` still keeps the takes until the team decides [72, 77, 87].
3. **Floor rule (d):** adopted in the app for iPhones (25 night 20/32 -> 30/32); still off for phones without a barometer, which need a held-out session with a healthy Android magnetometer [74, 90].
4. **Tian's night LT stops:** relabel to LT1B/LT1A? [73]
5. **Team review** of the 105 agent-drafted search queries and the guessed routing edges [57, 52-55].
6. **Never measured on site:** the 5F escalator landings, Y5-401's door, the 4F corridors, which LT is which [70].
7. **A scored live walk** with the truth noted [26, 86]: the protocol and blank score sheet are written (`phase2/new/live-walk/`, [92]), the walk itself is not done; a take that spans a floor change [74, 76].
8. **Report wording** about dropped user tests and no RAG is the team's to write [83, 84].
9. **Route planner** (entry 78, branch `feat/route-planner`, built, not yet landed): From / To or a tap on the plan, cheapest path with the metres of each leg, lift / stairs / escalator as separate connectors, Step-free mode (lifts and disabled toilets only), Male / Female / Any toilet filter, `/api/route` and `/api/nearest`. Still open: time the lift (42 s = 30 s wait + 12 s ride is a guess) and the escalators (20 s guess); confirm one lift next to the stairs on both floors, that 4F has no ordinary toilet, and step-free access along the routes [78].
