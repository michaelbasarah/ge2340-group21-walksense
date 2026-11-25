#!/usr/bin/env python3
"""Build test_queries.csv: the 23 starter queries (kept, expected IDs remapped to the graph-v2 place
IDs) plus a HARD set of agent-drafted queries, with a fixed dev/test split made BEFORE any method is run.

Every added row has source=agent_draft: the TEAM must review and edit them (course rule: the team
writes its own test phrases). Expected answers are the agent's best reading of the place list, not
field truth; rows with an uncertain reading carry a note.

expected syntax:  a place_id | several ids joined by '|' (any one is correct) | tag:<tag> (any place
with that tag is correct) | NONE (our list has no such place: the right answer is to reject).
Split: stratified by (set, category), random.Random(2340), about half of each group goes to dev.
Run:  python build_test_set.py
"""
import csv
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (query, expected) from test_queries_v1.csv; old IDs remapped to graph-v2 IDs (see PROCESS-LOG entry 71)
EASY = [
 ('where can I get food', 'canteen'), ('im hungry', 'canteen'), ('canteen', 'canteen'),
 ('somewhere to eat lunch', 'canteen'), ('nearest toilet', 'tag:toilet'), ('mens bathroom', 'male_toilet'),
 ('i need the washroom', 'tag:toilet'), ('how do I get out of here', 'tag:exit'), ('nearest exit', 'tag:exit'),
 ('way out', 'tag:exit'), ('the exit gate', 'entrance_exit'), ('pintu keluar', 'entrance_exit'),
 ('lecture theatre 2b', 'lt2b'), ('LT 1a', 'lt1a'), ('take me to lecture theatre 2a', 'lt2a'),
 ('study room 9', 'sr9'), ('sr11', 'sr9'), ('a quiet place to study', 'tag:study'),
 ('where can I study quietly', 'tag:study'), ('year 5 studio', 'y5302|y5202|y5401|y5302_back'),
 ('y4', 'y4502'), ('escalator', 'tag:escalator'), ('how do I go up a floor', 'tag:vertical'),
]

LIFT = 'lift_stairs|lift_stairs_4F'
H = {  # category -> [(query, expected, note)]
 'vague': [
  ('I need to print something', 'NONE', 'no printer in our list; team check'),
  ('quiet place to revise before my exam', 'sr9', ''),
  ('I need somewhere to focus for a few hours', 'sr9', ''),
  ('grab a bite', 'canteen', ''), ("I'm thirsty", 'canteen', ''),
  ('somewhere I can get a coffee', 'canteen', ''),
  ('where do I go for my class', 'tag:lecture', ''), ("I'm late for my lecture", 'tag:lecture', ''),
  ('emergency, where do I run', 'tag:emergency', ''), ('I need to wash my hands', 'tag:toilet', 'assumes toilets have sinks'),
  ('where can I sit and eat my packed lunch', 'canteen', ''),
  ('I want to go up to the next floor', 'tag:vertical', ''), ('how do I get to the floor below', 'tag:vertical', ''),
  ('somewhere to book for a group discussion', 'sr9', ''), ('I want to leave campus', 'tag:exit', ''),
  ('which way out to the MTR', 'tag:exit', 'which exit leads to the MTR is not in our data; any exit accepted'),
  ('take me home', 'tag:exit', ''), ('where do students usually have lunch', 'canteen', ''),
  ('I need to charge my phone', 'NONE', 'no charging place in our list'),
  ('where can I get something cold to drink', 'canteen', ''),
 ],
 'access': [
  ('wheelchair accessible toilet', 'disabled_toilet|disabled_toilet_4F', ''),
  ('I use a wheelchair, where is the toilet', 'disabled_toilet|disabled_toilet_4F', ''),
  ('step-free way to the other floor', LIFT, 'assumes the lift is step-free'),
  ('where is the lift', LIFT, ''), ('elevator please', LIFT, ''),
  ('accessible restroom on the lower floor', 'disabled_toilet_4F', ''),
  ("I can't use stairs, how do I get down to the lower floor", LIFT, ''),
  ('toilet for people with disabilities', 'disabled_toilet|disabled_toilet_4F', ''),
 ],
 'typo': [
  ('where is the cantene', 'canteen', ''), ('nearset tolet', 'tag:toilet', ''),
  ('lecure theater 2b', 'lt2b', ''), ('escelator', 'tag:escalator', ''), ('the exti', 'tag:exit', ''),
  ('study rom 9', 'sr9', ''), ('lecture theatre 1 b', 'lt1b', ''), ('restrom', 'tag:toilet', ''),
  ('canten', 'canteen', ''), ('wher can i eet', 'canteen', ''), ('lt2 a', 'lt2a', ''),
  ('washrom femail', 'female_toilet', ''), ('emrgency exit', 'tag:emergency', ''),
  ('where is the libary', 'NONE', 'typo of an unsupported place'), ('y 5302', 'y5302', ''), ('fod', 'canteen', ''),
  ('sr 9', 'sr9', ''), ('eskalator naik', 'escalator_up|escalator_up_4F', ''),
 ],
 'mixed': [
  ('kantin dimana', 'canteen', ''), ('mau makan dong', 'canteen', ''),
  ('toilet cowo dimana', 'male_toilet', ''), ('toilet cewe di mana', 'female_toilet', ''),
  ('esca naik', 'escalator_up|escalator_up_4F', ''), ('esca turun bawah', 'escalator_down_4F', 'bawah = lower floor (4F), as in the 25-Nov file names'),
  ('eska turun atas', 'escalator_down', 'atas = upper floor (5F)'), ('lt 2b di mana ya', 'lt2b', ''),
  ('pintu keluar dong', 'tag:exit', ''), ('sr9 dimana', 'sr9', ''), ('mau belajar yang sepi', 'sr9', ''),
  ('lapar banget, ada makanan?', 'canteen', ''), ('cari tangga atau lift', LIFT, ''),
  ('Y5302 dimana', 'y5302', ''), ('ke lantai bawah gimana', 'tag:vertical', ''),
  ('我想食嘢', 'canteen', 'Cantonese: I want to eat'), ('廁所喺邊度', 'tag:toilet', 'Cantonese: where is the toilet'),
  ('出口喺邊', 'tag:exit', 'Cantonese: where is the exit'), ('where got toilet ah', 'tag:toilet', ''),
  ('邊度可以讀書', 'sr9', 'Cantonese: where can I study'), ('I wanna sik faan', 'canteen', 'Cantonese sik faan = eat (a meal)'),
  ('返屋企點行', 'tag:exit', 'Cantonese: how do I go home'), ('電梯喺邊', 'tag:vertical', 'Cantonese: where is the lift/escalator'),
 ],
 'unsupported': [
  ('where is the library', 'NONE', ''), ('I need an ATM', 'NONE', ''), ('nearest gym', 'NONE', ''),
  ("where is the president's office", 'NONE', ''), ('how do I get to the bus stop', 'NONE', ''),
  ('lecture theatre 3a', 'NONE', 'we have LT1A, 1B, 2A, 2B only'), ('study room 12', 'NONE', 'we have SR8 to SR11 (merged as sr9)'),
  ('where can I buy a textbook', 'NONE', ''), ('tell me a joke', 'NONE', ''), ('what is the weather today', 'NONE', ''),
  ('y5501', 'NONE', 'not in our list'), ('where is the swimming pool', 'NONE', ''), ('toilet on floor 6', 'NONE', 'we have floors 4 and 5 only'),
  ('perpustakaan dimana', 'NONE', 'Indonesian: where is the library'), ('圖書館喺邊', 'NONE', 'Cantonese: where is the library'),
  ("take me to Prof Wong's office", 'NONE', ''), ('I feel sick, where is the clinic', 'NONE', 'no clinic in our list; team check'),
  ('parking lot', 'NONE', ''), ('is there a 7-eleven nearby', 'NONE', ''), ('where is the computer lab', 'NONE', 'not in our list; team check'),
  ('lecture theatre 3b', 'NONE', ''), ('how are you', 'NONE', ''), ('lt 4a', 'NONE', ''),
 ],
 'floor': [
  ('toilet on 4F', 'disabled_toilet_4F', 'only toilet in our list on 4F'), ('lift on the lower floor', 'lift_stairs_4F', ''),
  ('escalator going up from the lower floor', 'escalator_up_4F', ''), ('esc down on 5F', 'escalator_down', ''),
  ('exit 10 on floor 4', 'exit_10_4F', ''), ('the lift on the upper floor', 'lift_stairs', ''),
  ('exit 5 on 5F', 'exit_5', ''), ('exit 10 on the 5th floor', 'exit_10', ''),
 ],
 'indirect': [
  ('where do I find the Y5 rooms', 'y5302|y5202|y5401|y5302_back', ''), ('room y5-202', 'y5202', ''),
  ('the Y5 studio ending in 401', 'y5401', ''), ('the 502 studio on 4F', 'y4502', ''),
  ('point 2 behind Y5302', 'y5302_back', ''),
 ],
}

def main():
    rows = []
    for i, (q, e) in enumerate(EASY, 1):
        rows.append({'query': q, 'expected': e, 'set': 'easy', 'category': 'starter', 'source': 'starter_v1', 'note': ''})
    for cat, items in H.items():
        for q, e, n in items:
            rows.append({'query': q, 'expected': e, 'set': 'hard', 'category': cat, 'source': 'agent_draft', 'note': n})
    rng = random.Random(2340)
    groups = {}
    for r in rows:
        groups.setdefault((r['set'], r['category']), []).append(r)
    for key in sorted(groups):
        g = groups[key]; rng.shuffle(g)
        for j, r in enumerate(g):
            r['split'] = 'dev' if j < (len(g) + 1) // 2 else 'test'
    for i, r in enumerate(rows, 1):
        r['id'] = f'q{i:03d}'
    cols = ['id', 'query', 'expected', 'set', 'category', 'split', 'source', 'note']
    with (HERE / 'test_queries.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows([{c: r[c] for c in cols} for r in rows])
    from collections import Counter
    print(len(rows), Counter((r['set'], r['split']) for r in rows))
    print(Counter(r['expected'] == 'NONE' for r in rows))

if __name__ == '__main__':
    main()
