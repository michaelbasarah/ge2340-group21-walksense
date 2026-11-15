# WalkSense Phase 2: how the project works

GE2340 Group 21 (CityU, Sem A 2026/27)
Emmanuelle Sebastian Sanjaya, Chris Amadeus Putra Simatupang, Benedicta Amabel Riyadi, Michael Terence Basarah

Written Fri 6 Nov 2026. This is the overall plan. It does not hand out tasks to people. We split the work together on the first call.

> **Do not copy this plan into the report, slides or video script.** The course does not allow AI-generated text in what we submit, and parts of this plan were drafted with AI help. Use it as a checklist. Write the submitted text yourself, in your own words.

---

## 1. Where we are

- Phase 1 got **93/100**: Problem 19.5/20, Feasibility 26.5/30, Background 19/20, Impact + Writing 28/30.
- The TA's one warning: *"The six-week integration and testing schedule remains ambitious and needs careful planning."*
- Phase 2 is due **Mon 30 Nov, 23:59**. No late work is accepted. A late package scores 0.
- **We aim to submit on Sun 29 Nov**, one day early.
- We have about 3.5 weeks. That is less than the six weeks the proposal planned for.

## 2. Proposed scope (for the group to agree)

The TA said the schedule is tight, so this plan proposes a smaller area than the proposal. **This is a proposal, not a decision.**

| | Proposal (Phase 1) | Proposed for Phase 2 |
|---|---|---|
| Area | 2-3 floors of AC1 and AC2, plus the AC1-BOC-AC2 link | **2 floors of AC1**, joined by a lift and stairs |
| Checkpoints | about 80 | **about 40 per floor, about 80 in total** |
| Outdoor link | included | **only if time allows** |
| Destinations for request matching | about 30 | about 30 (matching is text only, so it does not depend on the mapped area) |

Why this still fits what we promised:
- The proposal's own fallback was **one floor**. Two floors is still above that.
- Two floors joined by a lift still tests the barometer and floor detection.
- We keep the same number of checkpoints, just packed into a smaller area.
- In the report we say clearly that we scoped down and why. That answers the TA's comment directly.

## 3. What we must hand in

One person submits **one package** for the whole group. If several people submit, only the latest one is graded. Check the Canvas page for the upload format (Phase 1 needed a single .zip).

| Item | Rules from the handout |
|---|---|
| **Report (PDF)** | 4 to 6 pages **including references**. Must use the LaTeX template. Keep the 6 section headings exactly as they are. Tables and figures for results. No big blocks of code; link a public GitHub repo instead. |
| **Video** | 12 to 15 minutes. Recorded on Zoom (or similar) with slides and demo on screen. The start must show **the topic and all 4 full names**. **Everyone shows their face and speaks.** Upload to Google Drive and submit the link. Test the link in an incognito window. |
| **Slides (PDF)** | The exact slides used in the video. Not too much text. Visuals that show our workflow. |
| **Contribution statement** | The mandatory template only. Signed by all four. Percentages add up to 100. Specific tasks per person, not "helped with the project". |
| **Extras (optional)** | Code, small data, links, images. Under 10 MB in total. Not an overflow appendix. |

The 6 report sections (headings must not change):
1. Introduction & Problem Recap
2. Data Collection & Methodology
3. Implementation Details
4. Results & Evaluation
5. Discussion
6. Conclusion

## 4. How we are graded

| Part | Points | What they look for |
|---|---|---|
| Execution & Findings | 30 | Data collection and AI actually done. **Unique discoveries** of our own (paraphrasing the internet loses points). Correct use of the methods. Teamwork. |
| Report | 30 | All sections, template followed, clear and concise, good tables and figures, correct citations. |
| Video | 20 | Shows the working solution. Clear speech. Stays within 12-15 min. |
| Slides | 20 | Looks good, flows well, readable, consistent style, balanced detail. |

- Failing the plagiarism check caps the score at **40**.
- Breaking format rules costs extra points.
- **Individual score = 60 + (group score - 60) x your % x 4.** Example: group score 90 and you have 25% gives 60 + 30 x 0.25 x 4 = 90. With 20% it gives 84.
- If the group score is below 60, everyone gets the group score.

## 5. The AI rules (read this part carefully)

Exact words from page 4 of the handout:

> "You are allowed to use Large Language Models (such as ChatGPT, DeepSeek, Gemini) to refine and polish your writing. You are NOT allowed to use these tools to generate text from scratch. In exceptional cases (e.g., if you are studying LLMs and need to demonstrate their output in your report), the outputs of these models must be explicitly quoted and cited."

> "Since we have no requirement for coding in this course, vibe coding is allowed in your implementation."

How we read it:

| Thing | AI allowed? |
|---|---|
| Code (Python, the demo, the "I'm here" page) | **Yes.** Vibe coding is allowed. |
| Charts and tables made by code from our real numbers | **Yes.** |
| The data | **No.** Every number must come from our own real recordings. |
| Report text, slide text, figure captions, video script | **Written by us.** AI may only polish what we already wrote. |
| LLM answers we test (request matching, LLM directions) | Shown in the report **in quotes, with a citation**. |

Habits that protect us:
- Write all drafts in **Google Docs**. The version history shows we wrote them.
- Do not paste this plan's wording into anything we submit.
- If you ask an AI to polish a paragraph, keep your original draft in the doc history.

## 6. What we promised to build

Everything below comes from our submitted proposal. Phase 2 is about doing it and measuring it.

### 6.1 Understanding the request (text matching)
A student types something like "AC2 canteen" or "a quiet place to study near LT-5". We match it to one place on our list of about 30 destinations. Three ways, compared on the same test set:
- **Keyword rules.** Simple and predictable. Misses vague requests.
- **Sentence embeddings.** A small pre-trained model that compares meaning. Handles vague requests.
- **An LLM that may only answer with a real place ID** from our list. Handles any phrasing. Needs internet.

### 6.2 Planning the route (search)
- **A\*** search on our hand-built map graph. Nodes are checkpoints, lifts, stairs and doors. Edges carry walking time.
- Compared with **an LLM given a text description of the floor plan** and asked for directions. We check whether its routes are real paths on our graph.

### 6.3 Knowing where the user is (positioning)
Four methods, all scored on the same test walks:

| | Method | Uses | Expected strength | Expected weakness |
|---|---|---|---|---|
| A | Dead reckoning | Step count + compass | No survey needed | Drifts over distance |
| B | Wi-Fi fingerprint (kNN or random forest) | Router signal strengths | No new hardware | Android only; crowds change signals |
| C | Magnetic fingerprint (kNN or random forest) | Magnetometer | Works on iPhone | Corridors that look alike magnetically |
| D | HMM fusion + barometer | A, B and C plus air pressure | Fixes drift, finds the floor | Most tuning |

### 6.4 What we measure

| Metric | Plain meaning |
|---|---|
| Matching accuracy | % of typed requests matched to the right place |
| Checkpoint accuracy | % of moments the system names the right checkpoint |
| Floor accuracy | % of moments it names the right floor |
| Position error (m) | How far, in metres, the guess is from where the person really was |
| Wrong-turn detection | How many metres a person walks off the route before the system notices |

### 6.5 The demo and user tests
- A **Streamlit** web page: type a request, see the route drawn on the floor plan, then watch a recorded walk replayed as if it were live tracking.
- **User tests** with 3 to 5 first-year students. They try the demo and we note what works and what confuses them.

## 7. How the technology works, in plain words

Your phone already has four sensors that can tell where it is indoors. No camera is needed.

- **Wi-Fi signal strength.** Every Wi-Fi router sends out an ID. The phone hears many of them, some strong and some weak. The pattern of strengths is different at each spot in the building, like a fingerprint. The phone does not need to connect to any network.
- **Magnetic field.** The steel in walls and floors bends the Earth's magnetic field. Each spot has its own slightly different reading. It stays stable over days and **works on iPhone**, which blocks Wi-Fi scanning.
- **Barometer.** Air pressure drops about **0.5 hPa per floor** you go up. That tells us the floor, even inside a lift.
- **Accelerometer.** Each step makes a small bounce. Counting bounces gives the number of steps.

**We are not building a phone app.** The phones only record, using free apps. All the AI runs afterwards in Python on a laptop.

| Tool | What it does | Phones |
|---|---|---|
| phyphox | Records magnetometer, barometer, accelerometer | Android and iPhone |
| WiGLE | Records Wi-Fi scans | Android only |
| "I'm here" page | A web page in the phone browser. Tap it at each checkpoint during a test walk. It saves the time. | Any |
| Python (pandas, scikit-learn, networkx, streamlit) | Cleaning, training, routing, demo | Laptop |

### The pipeline

```
ON THE PHONE (recording only)
  phyphox  -> magnetic field, air pressure, steps
  WiGLE    -> Wi-Fi router IDs and signal strengths
  "I'm here" page -> time of each checkpoint on test walks
        |
        v
  Google Drive: GE2340-Phase2/raw-data/
        |
        v
ON THE LAPTOP (all the AI, in Python)
  1. clean the files, cut each 30 s recording into 2 s slices
  2. train position classifier on days 1-2, test on day 3
  3. HMM tracker combines classifier + steps + barometer
  4. score against the test-walk ground truth

  typed request -> matcher -> place ID -> A* route on our map
        |
        v
  Streamlit demo: route on floor plan + replayed walk
```

## 8. What is trained and what is not

| Part | Trained? | How |
|---|---|---|
| Position classifier (kNN / random forest) | **Yes, on our recordings** | Each 30 s recording is cut into 2 s slices. Inputs: signal strength per router (a router we did not hear counts as "very weak"), magnetic strength and its x/y/z parts, and air pressure. The answer it learns: the checkpoint ID. |
| HMM tracker | Mostly set by hand, lightly tuned | Each step the person either stays at a checkpoint or moves to a neighbouring one. It cannot jump through walls. |
| A\* routing | No | It is a search algorithm. It just needs the map graph. |
| Request matching | No | Uses keyword rules, an existing embedding model, or an existing LLM. |

Two rules for training:
- **Train on days 1 and 2, test on day 3. Never mix days.** If the same day is in both, the scores look better than they really are.
- Training takes seconds on a laptop. **No GPU, no deep learning.**

## 9. How we collect the data

### 9.1 Map the floors
- Photograph the fire-exit floor plans on each floor.
- Put a checkpoint about every 4 m, at a landmark you can find again (a door, a pillar, a sign).
- Name each checkpoint like **AC1-3F-C12** (building, floor, checkpoint number).
- Keep one shared sheet with: ID, floor, x and y position in metres, and its neighbours.

### 9.2 Prepare the phones
- Install phyphox (all phones) and WiGLE (Android).
- **Android: turn OFF Wi-Fi scan throttling.** Settings, Developer options, "Wi-Fi scan throttling". If it stays on, the phone only scans about 4 times every 2 minutes, which is far too few.
- Charge the phone and clear space for files.

### 9.3 Pilot first (5 checkpoints)
Before the big sessions, record just 5 checkpoints and check the files. The main question: **does WiGLE's export keep EVERY scan, or only the best reading per router?** We need every scan.
- If WiGLE fails, the backup is **Termux + Termux:API** on Android, running `termux-wifi-scaninfo` every few seconds.
- The pilot also tells us how often Wi-Fi scans really arrive. If it is slower than every 2 s, some slices will share a scan.

### 9.4 Record the fingerprints
At each checkpoint:
- Hold the phone **flat**, always **pointing the same direction** (we agree the direction for each corridor in the sheet). The magnetic x/y/z readings change when the phone turns.
- Record for **30 seconds**.
- Name the file with the checkpoint ID, or write the start time in the sheet.
- Upload to **`GE2340-Phase2/raw-data/`** on Drive **the same day**.

Sessions:
- **At least 3 sessions on different days**, at different times (a busy time like lunch and a quiet time).
- Use **different phones and different people** across sessions.
- A full session of about 80 checkpoints takes about **1.5 hours**, so pairs split the floors.
- After each session, a **quick data check**: every checkpoint has a file, files open, names are right, Wi-Fi scans are there.

### 9.5 Test walks (the ground truth)
- On a **new day**, after the fingerprint sessions.
- **4 to 6 real routes**, including **lift rides** and **deliberate wrong turns**.
- Record continuously the whole way.
- Tap the **"I'm here"** button at each checkpoint you pass. Those timestamps are the true answer we score against.

### 9.6 Privacy
We record only router IDs, signal strengths and motion sensors. **No cameras, photos, audio or personal data.**

## 10. Who does what: people and the AI coding assistant

### People (all four of us)
- Mapping the floors and building the checkpoint sheet
- All recording sessions and test walks
- User tests with first-years
- The report text, slide text, captions and video script
- **Explaining WHY results happen.** This is where the "unique discoveries" points are. Possible examples, which we only claim if our data shows them: Wi-Fi is worse at lunch because of crowds; two corridors get confused because their steel layout is similar; one phone model reads pressure differently.

### The AI coding assistant (Claude Code, run by Michael)
It writes code in waves. Fake data is used **only to test that code runs**. It never appears in any result.

| Wave | What it builds |
|---|---|
| 1 | Code repo, file readers for phyphox and WiGLE, the checkpoint sheet template, a phone setup guide, the "I'm here" button page |
| 2a | Map graph from our sheet, A\* routing, drawing the route on the floor plan |
| 2b | Request matching (all three methods) and the test set format |
| 3 | Positioning pipeline (A to D) and scoring, then an independent check for data leakage and bugs |
| Later | Streamlit demo, results charts and tables from our real numbers, and a format check of the report (page count, headings) |

## 11. Timeline

Today is Fri 6 Nov. Deadline Mon 30 Nov 23:59.

| Dates | What happens |
|---|---|
| Fri 6 - Sun 8 Nov | Team call: agree scope, destinations, Drive folder. Pilot recording (5 checkpoints). Wave 1 code. |
| Sun 8 - Tue 10 Nov | Map both floors, fill the checkpoint sheet. A\* running on the real map. |
| Tue 10 - Sun 15 Nov | 3 recording sessions, data check after each. **Avoid Tue 10 Nov morning** (Michael has another presentation). |
| Mon 16 - Tue 17 Nov | Test walks. |
| Mon 16 - Fri 20 Nov | Train and compare A to D. Request matching tests. LLM directions test. Group review of results. |
| Fri 20 - Mon 23 Nov | Demo finished. User tests with 3 to 5 first-years. |
| Mon 23 - Fri 27 Nov | **Results frozen.** Each person writes their sections by hand. The writing lead merges and edits. Slides made. |
| Fri 27 - Sat 28 Nov | Rehearse and record the video. |
| **Sun 29 Nov** | Final checks and **submit**. |
| Mon 30 Nov 23:59 | Hard deadline (backup day only). |

The recording sessions are the bottleneck. If one is missed, everything after it gets squeezed.

## 12. Risks and what we do about them

| Risk | What we do |
|---|---|
| WiGLE's export does not keep every scan | Find out in the pilot. Switch to Termux + Termux:API. |
| People miss recording sessions | Book the session dates on the first call. Pairs cover floors, so one missing person does not stop a session. |
| iPhones cannot scan Wi-Fi | Magnetic and barometer still work on iPhone. That is part of the comparison. |
| Corridors that look alike | Fusion (D) uses the route so far to tell them apart. We report the confusions honestly. |
| Outdoor link has no fingerprints | Dead reckoning only. The link is optional anyway. |
| Report over 6 pages | Format check before submitting. Cut text before cutting figures. |

## 13. Decisions we need as a group

- [ ] **Scope:** 2 floors of AC1 joined by lift and stairs, link only if time allows? Which two floors?
- [ ] **Destinations:** the list of about 30 places, with tags like "quiet" or "food".
- [ ] **Session dates:** 3 fingerprint sessions (mix of busy and quiet times) and 1 test-walk day.
- [ ] **Phones:** which Android and iPhone models we use, and who can bring them.
- [ ] **Drive folder:** create `GE2340-Phase2/` with `raw-data/` and share it with all four.
- [ ] **GitHub repo:** public or not? The handout says to link a public repo if there is a lot of code.

## 14. Final submission checklist

Report
- [ ] LaTeX template, 6 headings unchanged
- [ ] 4 to 6 pages including references
- [ ] All numbers come from our real recordings
- [ ] Tables and figures have captions written by us
- [ ] LLM outputs we show are quoted and cited
- [ ] References cited in the text
- [ ] GitHub link (and demo link if any) at the top

Video
- [ ] 12 to 15 minutes
- [ ] Opens with the topic and all 4 full names
- [ ] All four show their face and speak
- [ ] Shows the working demo
- [ ] Uploaded to Google Drive, link opens in an incognito window without logging in

Slides
- [ ] PDF of the exact slides used in the video

Contribution statement
- [ ] Mandatory template
- [ ] Percentages add up to 100
- [ ] Specific tasks for each person
- [ ] Signed by all four

Package
- [ ] Optional extras under 10 MB
- [ ] One person submits, on Sun 29 Nov
- [ ] Everyone checks the submitted files open
