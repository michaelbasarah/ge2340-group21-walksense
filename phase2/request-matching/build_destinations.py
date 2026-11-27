#!/usr/bin/env python3
"""Build destinations.csv from the real place list.

Sources (read, not copied by hand):
  ../new/graph-v2/nodes.csv        the 26 real places (virtual midpoints skipped), floor, kind
  ../new/upload/map/places.json    the labels Tian's app uses (key per floor); every key is checked
The names/aliases/tags below are an AGENT DRAFT for the team to review and edit (course rule:
the team writes its own text; these are matching keywords, not report text).
Run:  python build_destinations.py     (standard library only)
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NODES = HERE.parent / 'new' / 'graph-v2' / 'nodes.csv'
MAP = HERE.parent / 'new' / 'upload' / 'map' / 'places.json'

TOILET_GENERIC = 'toilet;bathroom;washroom;restroom;wc;lavatory;loo;pee;poo;toilets;kamar kecil;kamar mandi'
EXIT_GENERIC = 'exit;exits;way out;get out;pintu keluar;keluar'
ESC_GENERIC = 'escalator;escalators;eskalator;esca;eska;moving stairs;change floor;ganti lantai'
LT_GENERIC = 'lecture theatre;lecture theater;lecture hall;lecture;class;lesson;kuliah;ruang kuliah;kelas'
Y5_GENERIC = 'y5;year 5;studio 5'

# place_id: (display name, map_key in places.json (same floor), tags, aliases)
P = {
 'canteen': ('Canteen (5F)', 'canteen', 'food;drink',
   'canteen;kantin;cafeteria;food court;food;eat;hungry;lunch;dinner;breakfast;meal;rice;noodles;'
   'siu mei;roast meat;char siu;dim sum;drink;coffee;snack;city express;makan;lapar;makan siang'),
 'exit_5': ('Exit 5 (5F)', 'exit5_door', 'exit;emergency',
   'exit 5;exit5;emergency exit;emergency;emergency case;fire exit;fire;evacuate;alarm;emergency stairs;' + EXIT_GENERIC),
 'male_toilet': ('Male toilet (5F)', 'male_toilet', 'toilet;male',
   'male toilet;mens toilet;mens;mens bathroom;men toilet;gents;toilet cowo;toilet laki;wc cowo;cowo;' + TOILET_GENERIC),
 'y5302': ('Y5-302 (5F)', 'y5302', 'room;studio',
   'y5302;y5 302;y5-302;y5 studio;' + Y5_GENERIC),
 'sr9': ('Study rooms SR8 to SR11 (merged as SR9, book first)', 'sr9', 'study;quiet;bookable;room',
   'sr9;study room 9;room 9;sr8;sr10;sr11;study room 8;study room 10;study room 11;study room;study rooms;'
   'quiet study;ruang belajar;belajar;revise;revision;study;quiet place'),
 'y5202': ('Y5-202 (5F)', 'y5202', 'room;studio',
   'y5202;y5 202;y5-202;' + Y5_GENERIC),
 'female_toilet': ('Female toilet (5F)', 'female_toilet', 'toilet;female',
   'female toilet;womens toilet;womens;ladies;toilet cewe;toilet perempuan;wc cewe;cewe;' + TOILET_GENERIC),
 'exit_10': ('Exit 10 (5F)', 'exit10_door', 'exit;emergency',
   'exit 10;exit10;' + EXIT_GENERIC),
 'escalator_up': ('Escalator up (5F)', 'esca_up', 'escalator;vertical;floor_change',
   'escalator up;esca up;esca naik;eska naik;eskalator naik;up escalator;go up;going up;upstairs;naik;' + ESC_GENERIC),
 'escalator_down': ('Escalator down (5F)', 'esca_down', 'escalator;vertical;floor_change',
   'escalator down;esca down;esca turun;eska turun;eskalator turun;down escalator;go down;going down;downstairs;turun;' + ESC_GENERIC),
 'disabled_toilet': ('Male disabled toilet (5F)', 'male_disabled_toilet', 'toilet;accessible;wheelchair',
   'disabled toilet;male disabled toilet;male disabled toilet 5f;accessible toilet;wheelchair toilet;handicap toilet;toilet disabilitas;toilet difabel;' + TOILET_GENERIC),
 'y5401': ('Y5-401 (5F)', 'y5401', 'room;studio',
   'y5401;y5 401;y5-401;' + Y5_GENERIC),
 'y5302_back': ('Y5-302 back, point 2 (5F)', 'y5302_point2', 'room;studio',
   'y5302 back;y5302 point 2;back of y5302;y5 302 back;' + Y5_GENERIC),
 'lift_stairs': ('Lift and stairs (5F)', 'lift_stairs5', 'lift;stairs;vertical;floor_change;accessible',
   'lift;elevator;lift and stairs;stairs;staircase;tangga;lift naik;go up;upstairs;downstairs;change floor;ganti lantai'),
 'disabled_toilet_4F': ('Mixed disabled toilet (4F)', 'disabled_toilet', 'toilet;accessible;wheelchair',
   'disabled toilet 4f;mixed disabled toilet;mixed disabled toilet 4f;unisex accessible toilet;toilet 4f;4f toilet;disabled toilet bawah;toilet bawah;' + TOILET_GENERIC),
 'exit_5_4F': ('Exit 5 (4F)', 'exit5_door', 'exit;emergency',
   'exit 5 4f;exit 5 bawah;exit 5 lantai 4;emergency exit 4f;' + EXIT_GENERIC),
 'lt2a': ('Lecture theatre 2A (4F)', 'lt2a', 'lecture',
   'lt2a;lt 2a;lecture theatre 2a;lecture 2a;theatre 2a;kelas 2a;' + LT_GENERIC),
 'lt2b': ('Lecture theatre 2B (4F)', 'lt2b', 'lecture',
   'lt2b;lt 2b;lecture theatre 2b;lecture 2b;theatre 2b;kelas 2b;' + LT_GENERIC),
 'escalator_down_4F': ('Escalator down (4F)', 'esca_down', 'escalator;vertical;floor_change',
   'escalator down 4f;esca turun bawah;eska turun bawah;down escalator 4f;go down;going down;downstairs;turun;' + ESC_GENERIC),
 'y4502': ('Y4-502 (4F)', 'y4502', 'room;studio',
   'y4502;y4 502;y4-502;y4;year 4;studio 4;y4 studio'),
 'escalator_up_4F': ('Escalator up (4F)', 'esca_up', 'escalator;vertical;floor_change',
   'escalator up 4f;esca naik bawah;eska naik bawah;up escalator 4f;go up;going up;upstairs;naik;' + ESC_GENERIC),
 'lt1b': ('Lecture theatre 1B (4F)', 'lt1b', 'lecture',
   'lt1b;lt 1b;lecture theatre 1b;lecture 1b;theatre 1b;kelas 1b;' + LT_GENERIC),
 'lt1a': ('Lecture theatre 1A (4F)', 'lt1a', 'lecture',
   'lt1a;lt 1a;lecture theatre 1a;lecture 1a;theatre 1a;kelas 1a;' + LT_GENERIC),
 'exit_10_4F': ('Exit 10 (4F)', 'exit10_door', 'exit;emergency',
   'exit 10 4f;exit 10 bawah;exit 10 lantai 4;' + EXIT_GENERIC),
 'entrance_exit': ('Entrance / exit gate (4F)', 'gate', 'exit;gate;entrance;emergency',
   'gate;exit gate;main exit;main entrance;entrance;turnstile;pintu keluar;pintu masuk;leave the building;leave building;'
   'exit the building;exit building;way out of the building;go home;go outside;outside;' + EXIT_GENERIC),
 'lift_stairs_4F': ('Lift and stairs (4F)', 'lift_stairs5', 'lift;stairs;vertical;floor_change;accessible',
   'lift 4f;lift bawah;stairs 4f;lift and stairs 4f;lift;elevator;stairs;staircase;tangga;go up;upstairs;downstairs;change floor'),
}

def main():
    nodes = [r for r in csv.DictReader(NODES.open(encoding='utf-8')) if r['virtual'] == '0']
    maps = json.loads(MAP.read_text(encoding='utf-8'))
    ids = [r['node_id'] for r in nodes]
    assert set(ids) == set(P), (set(ids) ^ set(P))
    out = []
    for r in nodes:
        name, mk, tags, aliases = P[r['node_id']]
        assert mk in maps[r['floor']]['places'], (r['node_id'], mk)     # label exists in Tian's app on that floor
        al = []
        for a in aliases.split(';'):
            a = a.strip()
            if a and a not in al:
                al.append(a)
        out.append({'place_id': r['node_id'], 'name': name, 'floor': r['floor'], 'kind': r['kind'],
                    'map_key': mk, 'tags': tags, 'aliases': ';'.join(al)})
    with (HERE / 'destinations.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(len(out), 'places written to destinations.csv')

if __name__ == '__main__':
    main()
