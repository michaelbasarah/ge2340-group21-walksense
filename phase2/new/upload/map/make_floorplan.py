#!/usr/bin/env python3
"""Vector floor plan (metres) for the upload page: map/floorplan.json, drawn by map/floorplan.js.

Two steps:
  python make_floorplan.py trace   # needs pymupdf: reads the sketch PDF -> map/sketch_trace.json (committed)
  python make_floorplan.py         # numpy + scipy only: sketch_trace.json + graph.json + Google pins -> floorplan.json

Where the geometry comes from (PROCESS-LOG entry "vector floor plan"):
- The sketch PDF (phase2/clean-data/2026-11-24/floor-sketch-v1.pdf) is the collector's drawing ON a Google
  indoor-map screenshot, one page per floor. From the PDF we read: the red stop dots and the black corridor
  lines (exact vector coordinates), the typed 4F metre marks, and the screenshot itself. The screenshot is
  segmented by its flat Google colours into rooms (beige), corridors (white), toilets (blue) and
  escalators/stair cores (grey), and each region is traced to a polygon.
- Metres: x east, y north, the frame of phase2/map/coordinates_meters.csv (Google lat/long of 8 floor-5 places,
  phase2/map/build_map.py). A similarity transform (scale, rotation, shift) from 5F screenshot pixels to that
  frame is fitted on those 8 places. The 4F screenshot is put into the 5F screenshot's pixels with the two Google
  markers visible on both (City Express, Y5ZONE), then the same transform.
- Place points: a small least-squares layout. Unknowns = every place and corridor bend; terms = the Google pins
  (5F, 8 places), the corridor lengths of phase2/new/routing/graph.json (weighted by their source: measured,
  steps, guess) and the sketch position (weak prior that keeps the shape). The residual of every edge is written.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PDF = REPO / 'phase2' / 'clean-data' / '2026-11-24' / 'floor-sketch-v1.pdf'
GRAPH = REPO / 'phase2' / 'new' / 'routing' / 'graph.json'
PINS = REPO / 'phase2' / 'map' / 'coordinates_meters.csv'
TRACE = HERE / 'sketch_trace.json'
OUT = HERE / 'floorplan.json'
PAGE_OF = {5: 0, 4: 1}

# ------------------------------------------------------------------ ids: model place (per floor) <-> graph.json
GRAPH_ID = {5: {'canteen': 'canteen', 'exit5_door': 'exit_5', 'male_toilet': 'male_toilet', 'y5302': 'y5302',
                'sr9': 'sr9', 'y5202': 'y5202', 'female_toilet': 'female_toilet', 'exit10_door': 'exit_10',
                'esca_up': 'escalator_up', 'esca_down': 'escalator_down', 'male_disabled_toilet': 'disabled_toilet',
                'lift_stairs5': 'lift_stairs', 'y5401': 'y5401', 'y5302_point2': 'y5302_back'},
            4: {'lift_stairs5': 'lift_stairs_4F', 'exit5_door': 'exit_5_4F', 'lt2a': 'lt2a', 'lt2b': 'lt2b',
                'esca_down': 'escalator_down_4F', 'y4502': 'y4502', 'esca_up': 'escalator_up_4F', 'lt1b': 'lt1b',
                'lt1a': 'lt1a', 'exit10_door': 'exit_10_4F', 'gate': 'entrance_exit', 'disabled_toilet': 'disabled_toilet_4F'}}
# Display names (user-confirmed 26 Nov: the 5F disabled toilet is male, the 4F one is mixed) and short map labels.
NAMES = {5: {'canteen': ('Canteen entrance', 'Canteen'), 'exit5_door': ('Exit 5 (emergency exit)', 'Exit 5'),
             'male_toilet': ('Male toilet', 'Male WC'), 'y5302': ('Room Y5-302 (front door)', 'Y5-302'),
             'sr9': ('Study rooms (Y5-511 to Y5-514)', 'Study rooms'), 'y5202': ('Room Y5-202', 'Y5-202'),
             'female_toilet': ('Female toilet', 'Female WC'), 'exit10_door': ('Exit 10 (by the toilets)', 'Exit 10'),
             'esca_up': ('Up escalator (5F)', 'Esc. up'), 'esca_down': ('Down escalator (5F)', 'Esc. down'),
             'male_disabled_toilet': ('Male disabled toilet (5F)', 'Disabled WC'),
             'lift_stairs5': ('Lift and stairs (5F)', 'Lift / stairs'), 'y5401': ('Room Y5-401', 'Y5-401'),
             'y5302_point2': ('Room Y5-302 (back door)', 'Y5-302 back')},
         4: {'lift_stairs5': ('Lift and stairs (4F)', 'Lift / stairs'), 'exit5_door': ('Exit 5 (4F)', 'Exit 5'),
             'lt2a': ('LT2A', 'LT2A'), 'lt2b': ('LT2B', 'LT2B'), 'esca_down': ('Down escalator (4F)', 'Esc. down'),
             'y4502': ('Room Y4-502', 'Y4-502'), 'esca_up': ('Up escalator (4F)', 'Esc. up'), 'lt1b': ('LT1B', 'LT1B'),
             'lt1a': ('LT1A', 'LT1A'), 'exit10_door': ('Exit 10 (4F)', 'Exit 10'),
             'gate': ('Entrance gate (4F)', 'Gate'), 'disabled_toilet': ('Mixed disabled toilet (4F)', 'Disabled WC')}}
KIND = {'canteen': 'room', 'exit5_door': 'exit', 'male_toilet': 'toilet', 'y5302': 'room', 'sr9': 'room', 'y5202': 'room',
        'female_toilet': 'toilet', 'exit10_door': 'exit', 'esca_up': 'escalator', 'esca_down': 'escalator',
        'male_disabled_toilet': 'toilet', 'disabled_toilet': 'toilet', 'lift_stairs5': 'lift_stairs', 'y5401': 'room',
        'y5302_point2': 'room', 'lt1a': 'room', 'lt1b': 'room', 'lt2a': 'room', 'lt2b': 'room', 'y4502': 'room', 'gate': 'exit'}
PIN_NAME = {'Exit 5 (emergency exit)': 'exit5_door', 'Exit by bathroom (emergency)': 'exit10_door', 'Canteen (entrance)': 'canteen',
            'Male toilet': 'male_toilet', 'Female toilet': 'female_toilet', 'Y5-202': 'y5202', 'Y5-302': 'y5302',
            'Study Room 9 (Y5-512)': 'sr9'}

# ------------------------------------------------------------------ sketch reading (page units of the PDF, 1440 x 810)
# Which red dot is which place: make_map.py REF (PROCESS-LOG entry 25). The 4F disabled toilet has no dot: it is put
# at the 5F offset (Exit 5 -> disabled toilet), which lands at the door of Google's 4F "Wheelchair Accessible Bathroom".
REF = {5: {'canteen': (328, 282), 'exit5_door': (228, 376), 'male_toilet': (277, 412), 'y5302': (368, 502),
           'sr9': (486, 420), 'y5202': (563, 304), 'female_toilet': (468, 214), 'exit10_door': (430, 181),
           'esca_up': (390, 294), 'esca_down': (354, 333), 'male_disabled_toilet': (210, 394),
           'lift_stairs5': (170, 472), 'y5401': (203, 516), 'y5302_point2': (282, 592)},
       4: {'lift_stairs5': (172, 512), 'exit5_door': (230, 412), 'lt2a': (298, 414), 'lt2b': (437, 554),
           'esca_down': (466, 474), 'y4502': (572, 516), 'esca_up': (527, 417), 'lt1b': (602, 376),
           'lt1a': (466, 243), 'exit10_door': (449, 184), 'gate': (350, 289)}}
INFERRED_DOT = {4: {'disabled_toilet': 'exit5_door'}}       # placed at the 5F offset from this place
# Corridor bends drawn in the sketch (page units, from the black vector lines).
BENDS = {5: {'b_y5302_sr9': (445, 464), 'b_sr9_y5202': (532, 377), 'b_exit5_lift': (153, 453)},
         4: {'b_exit5_lift': (153, 493)}}
# Corridor of every graph edge as a list of points (place ids or bends); edges not drawn in the sketch are marked.
PATHS = {5: [('canteen', 'exit5_door'), ('exit5_door', 'male_toilet'), ('male_toilet', 'y5302'),
             ('y5302', 'b_y5302_sr9', 'sr9'), ('sr9', 'b_sr9_y5202', 'y5202'), ('y5202', 'female_toilet'),
             ('female_toilet', 'exit10_door'), ('exit10_door', 'esca_up'), ('esca_up', 'esca_down'),
             ('esca_down', 'exit5_door'), ('exit10_door', 'canteen'), ('canteen', 'esca_down'), ('esca_up', 'canteen'),
             ('exit5_door', 'male_disabled_toilet'), ('male_disabled_toilet', 'b_exit5_lift', 'lift_stairs5'),
             ('lift_stairs5', 'y5401'), ('y5401', 'y5302_point2'), ('y5302_point2', 'y5401', 'lift_stairs5')],
         4: [('lift_stairs5', 'b_exit5_lift', 'disabled_toilet'), ('disabled_toilet', 'exit5_door'), ('exit5_door', 'lt2a'),
             ('lt2a', 'lt2b'), ('lt2b', 'esca_down'), ('esca_down', 'y4502'), ('y4502', 'esca_up'), ('esca_up', 'lt1b'),
             ('lt1b', 'lt1a'), ('lt1a', 'exit10_door'), ('exit10_door', 'gate'), ('gate', 'exit5_door'), ('esca_down', 'esca_up')]}
NOT_IN_SKETCH = {(5, 'exit10_door', 'esca_up'): 'not drawn in the sketch: straight line (guess)',
                 (5, 'esca_down', 'exit5_door'): 'not drawn in the sketch: straight line across the open area',
                 (5, 'y5302_point2', 'lift_stairs5'): 'not drawn: same corridor as Y5-302 back -> Y5-401 -> lift'}
# Metre marks the collector wrote on the sketch. 4F typed ones come from the PDF text; handwriting read by eye.
MARKS = {5: {('exit10_door', 'canteen'): '11.9', ('canteen', 'exit5_door'): '11.9', ('female_toilet', 'exit10_door'): '6',
             ('y5202', 'female_toilet'): '10', ('sr9', 'y5202'): '11', ('y5302', 'sr9'): '11', ('male_toilet', 'y5302'): '10',
             ('exit5_door', 'male_toilet'): '6', ('esca_up', 'canteen'): '4.9', ('canteen', 'esca_down'): '4.9',
             ('esca_up', 'esca_down'): '3.9', ('exit5_door', 'male_disabled_toilet'): '1 (handwriting, unclear)',
             ('male_disabled_toilet', 'lift_stairs5'): '7 + 3', ('lift_stairs5', 'y5401'): '4', ('y5401', 'y5302_point2'): '9'},
         4: {('exit5_door', 'gate'): '11.43', ('gate', 'exit10_door'): '11.43', ('exit5_door', 'lt2a'): '4.7',
             ('lift_stairs5', 'disabled_toilet'): '9.1 + 1.? (whole Exit 5 -> lift line; handwriting)',
             ('lt2a', 'lt2b'): '15', ('lt1b', 'lt1a'): '15', ('lt1a', 'exit10_door'): '4.77', ('esca_down', 'y4502'): '9.38',
             ('y4502', 'esca_up'): '9.38', ('esca_up', 'lt1b'): '6.76', ('esca_down', 'esca_up'): '6.34'}}

# Landmark footprints: seed pixels (in each floor's own screenshot) of the traced Google regions that belong to a place.
FOOTPRINTS = {
    5: [('canteen', 'Canteen (City Express)', 'room', [(150, 150)], ''),
        ('female_toilet', 'Female toilet', 'toilet', [(510, 175), (440, 160)], ''),
        ('male_toilet', 'Male toilet', 'toilet', [(235, 465)], 'Google labels this block "Female Bathroom"; the team stop here is the male toilet. Confirm on site.'),
        ('male_disabled_toilet', 'Male disabled toilet', 'toilet', [(205, 395)], 'small toilet block next to the stop; matches the 4F wheelchair toilet above it'),
        ('esca', 'Escalators', 'escalator', [(365, 310), (400, 335), (420, 375), (380, 290)], 'two escalator strips'),
        ('lift_stairs5', 'Stairs', 'lift_stairs', [(130, 470)], 'grey stair block by the stop (Google stairs icon); the lift is not shown on Google'),
        ('y5302', 'Y5-302', 'room', [(285, 500)], ''),
        ('sr9', 'Study rooms Y5-511..514', 'room', [(520, 400), (497, 422), (472, 444), (447, 467)], ''),
        ('y5401', 'Y5-401', 'room', [(190, 545)], '')],
    4: [('lt1a', 'LT1A', 'room', [(560, 200)], 'nearest Google room: Tin Ka Ping Lecture Theatre (confirm the LT name)'),
        ('lt1b', 'LT1B', 'room', [(720, 320)], 'nearest Google room: CY Sun Lecture Theatre (confirm the LT name)'),
        ('lt2a', 'LT2A', 'room', [(230, 540)], 'nearest Google room: Mr and Mrs Sze Chi Ching Lecture Theatre (confirm)'),
        ('lt2b', 'LT2B', 'room', [(370, 690)], 'nearest Google room: Mr & Mrs David TF Chow Lecture Theatre (confirm)'),
        ('y4502', 'Y4-502', 'room', [(540, 470)], 'nearest Google room: Photo Copying Centre; Y4-502 is not named on Google (inferred)'),
        ('disabled_toilet', 'Mixed disabled toilet', 'toilet', [(200, 395)], 'Google: Wheelchair Accessible Bathroom'),
        ('esca', 'Escalators', 'escalator', [(350, 300), (420, 345), (400, 395)], 'escalator strips'),
        ('lift_stairs5', 'Stairs', 'lift_stairs', [(160, 480)], 'grey stair block by the stop (Google stairs icon); the lift is not shown on Google')]}
GOOGLE_COL = {'room': (253, 249, 239), 'white': (255, 255, 255), 'out': (248, 247, 247), 'light': (248, 249, 250),
              'grey': (241, 243, 244), 'blue': (224, 229, 255)}
# Label direction overrides (unit vector, x east / y north) where the automatic "away from the middle" crowds.
LABEL_DIR = {4: {'disabled_toilet': (0.2, -1.0), 'lift_stairs5': (0.3, -1.0)}}
MARGIN_M = 6.0           # context drawn around the places
FOOT_MARGIN_M = 13.0     # named footprints may reach this far out (the view grows to show them)


# ============================================================================ step 1: trace the PDF
def _dp(pts, tol):
    """Douglas-Peucker simplification of an open polyline."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    n = np.hypot(*ab)
    if n < 1e-9:                                       # closed ring: split at the point farthest from the start
        i = int(np.argmax(np.hypot(*(pts - a).T)))
        return np.vstack([_dp(pts[:i + 1], tol)[:-1], _dp(pts[i:], tol)])
    d = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / n
    i = int(np.argmax(d))
    if d[i] <= tol:
        return np.array([a, b])
    return np.vstack([_dp(pts[:i + 1], tol)[:-1], _dp(pts[i:], tol)])


def _polygons(mask, tol=1.2, min_px=150):
    import contourpy
    from scipy import ndimage as ndi
    z = np.pad(mask.astype(float), 1)
    z = ndi.gaussian_filter(z, 0.6)
    out = []
    for line in contourpy.contour_generator(z=z, line_type='Separate').lines(0.5):
        line = line - 1.0                                  # undo the padding
        if len(line) < 4:
            continue
        x, y = line[:, 0], line[:, 1]
        area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        if area < min_px:
            continue
        s = _dp(line, tol)
        if len(s) >= 4:
            out.append({'area_px': round(float(area)), 'pts': [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in s[:-1]]})
    return out


def _segment(img):
    names = list(GOOGLE_COL)
    c = np.array([GOOGLE_COL[k] for k in names])
    d = np.abs(img[:, :, None, :].astype(int) - c[None, None]).sum(-1)
    lab = np.where(d.min(-1) <= 4, d.argmin(-1), -1)
    return {k: lab == i for i, k in enumerate(names)}


def trace():
    import pymupdf
    from scipy import ndimage as ndi
    doc = pymupdf.open(PDF)
    tr = {'source': str(PDF.relative_to(REPO)), 'floors': {}}
    for floor, pno in PAGE_OF.items():
        page = doc[pno]
        (xref, *_), = page.get_images(full=True)
        rect = page.get_image_rects(xref)[0]
        pix = pymupdf.Pixmap(doc, xref)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
        sx, sy = pix.w / rect.width, pix.h / rect.height
        to_img = lambda p: (round((p[0] - rect.x0) * sx, 2), round((p[1] - rect.y0) * sy, 2))
        dots = []
        for dr in page.get_drawings():
            f = dr.get('fill')
            if f and f[0] > 0.9 and f[1] < 0.5 and f[2] < 0.5:
                r = dr['rect']
                dots.append(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
        places = {}
        for node, ref in REF[floor].items():
            d = min(dots, key=lambda p: np.hypot(p[0] - ref[0], p[1] - ref[1]))
            assert np.hypot(d[0] - ref[0], d[1] - ref[1]) < 15, (floor, node)
            places[node] = to_img(d)
        assert len(set(places.values())) == len(places) == len(dots), (floor, len(dots))
        lines = [[to_img(q) for q in (it[1], it[2])] for dr in page.get_drawings()
                 if dr.get('color') == (0.0, 0.0, 0.0) and dr.get('fill') is None for it in dr['items'] if it[0] == 'l']
        seg = _segment(img)
        # Google markers present on both floors' screenshots (used to put 4F into the 5F pixels).
        r, g, b = (img[:, :, k].astype(int) for k in range(3))
        orange = (r > 220) & (g > 90) & (g < 150) & (b < 60)
        ys, xs = np.nonzero(orange)
        k = (ys < 300) & (xs < 320)
        pin = (r == 120) & (g == 144) & (b == 156)
        ys2, xs2 = np.nonzero(pin)
        k2 = (xs2 < 130) & (ys2 > 300) & (ys2 < 380)
        markers = {'city_express': [round(float(xs[k].mean()), 2), round(float(ys[k].mean()), 2)],
                   'y5zone': [round(float(xs2[k2].mean()), 2), round(float(ys2[k2].mean()), 2)]}
        walk = ndi.binary_closing(seg['white'] | seg['light'], np.ones((7, 7)))
        walk = ndi.binary_opening(walk, np.ones((3, 3)))
        regions = []
        for kind, m in (('room', seg['room']), ('toilet', seg['blue']), ('grey', seg['grey']), ('light', seg['light'])):
            cc, n = ndi.label(m)
            for i in range(1, n + 1):
                comp = cc == i
                if comp.sum() < 120:
                    continue
                for p in _polygons(ndi.binary_fill_holes(ndi.binary_closing(comp, np.ones((3, 3))) | comp)):   # text holes filled
                    regions.append({'kind': kind, 'comp': f'{kind}{i}', **p})
        seeds = {}
        masks = {'room': seg['room'], 'toilet': seg['blue'], 'escalator': seg['grey'], 'lift_stairs': seg['grey']}
        for fid, _, kind, pts, _ in FOOTPRINTS[floor]:
            m = masks[kind]
            cc, _ = ndi.label(m)
            mk = {'room': 'room', 'toilet': 'toilet', 'escalator': 'grey', 'lift_stairs': 'grey'}[kind]
            comps = []
            for (x, y) in pts:                             # seeds sit on Google's text: snap to the nearest pixel
                ys, xs = np.nonzero(m)
                d = np.hypot(xs - x, ys - y)
                i = int(np.argmin(d))
                assert d[i] < 10, (floor, fid, (x, y))
                comps.append(f'{mk}{cc[ys[i], xs[i]]}')
            seeds[fid] = sorted(set(comps))
        tr['floors'][str(floor)] = {
            'image_px': [pix.w, pix.h], 'page_rect': [rect.x0, rect.y0, rect.x1, rect.y1], 'dots': places,
            'bends': {k: to_img(v) for k, v in BENDS[floor].items()}, 'lines': lines, 'markers': markers,
            'text': [{'text': s['text'], 'bbox': [round(v, 1) for v in s['bbox']]} for blk in page.get_text('dict')['blocks']
                     for ln in blk.get('lines', []) for s in ln['spans']],
            'walkable': _polygons(walk, tol=1.5, min_px=400), 'regions': regions, 'footprint_comps': seeds}
        print(f'{floor}F: {len(places)} dots, {len(lines)} lines, {len(regions)} regions, '
              f"{len(tr['floors'][str(floor)]['walkable'])} walkable polygons")
    TRACE.write_text(json.dumps(tr, separators=(',', ':')))


# ============================================================================ step 2: fit and write floorplan.json
def similarity(P, Q):
    """Q ~ s R P + t (no reflection). Returns s, R, t."""
    mp, mq = P.mean(0), Q.mean(0)
    A, B = P - mp, Q - mq
    U, S, Vt = np.linalg.svd(A.T @ B)
    R = (U @ Vt).T
    assert np.linalg.det(R) > 0
    s = S.sum() / (A ** 2).sum()
    return s, R, mq - s * R @ mp


def poly_len(pts):
    p = np.asarray(pts, float)
    return float(np.hypot(*np.diff(p, axis=0).T).sum())


def clip(poly, box):
    """Sutherland-Hodgman clip of a polygon to [x0, y0, x1, y1]."""
    x0, y0, x1, y1 = box
    for inside, cut in ((lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
                        (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
                        (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
                        (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1))):
        out = []
        for i, b in enumerate(poly):
            a = poly[i - 1]
            if inside(b):
                if not inside(a):
                    out.append(cut(a, b))
                out.append(b)
            elif inside(a):
                out.append(cut(a, b))
        poly = out
        if not poly:
            break
    return poly


def _area(p):
    x, y = np.asarray(p, float).T
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def _hull(p):
    """Convex hull (monotone chain)."""
    pts = sorted(set(map(tuple, p)))
    if len(pts) < 3:
        return pts
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for q in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], q) <= 0:
            hi.pop()
        hi.append(q)
    return lo[:-1] + hi[:-1]


def build():
    from scipy.optimize import least_squares
    tr = json.loads(TRACE.read_text())
    graph = json.loads(GRAPH.read_text())
    gedge = {}
    for e in graph['edges']:
        gedge[(e['from'], e['to'])] = e
    pins = {PIN_NAME[r['checkpoint']]: (float(r['x_m']), float(r['y_m'])) for r in csv.DictReader(PINS.open())
            if r['checkpoint'] in PIN_NAME}

    # pixel frames: 4F screenshot -> 5F screenshot pixels via the two shared Google markers
    f5, f4 = tr['floors']['5'], tr['floors']['4']
    m5 = np.array([f5['markers']['city_express'], f5['markers']['y5zone']])
    m4 = np.array([f4['markers']['city_express'], f4['markers']['y5zone']])
    s54, R54, t54 = similarity(m4, m5)
    to5px = {5: lambda p: np.asarray(p, float), 4: lambda p: (s54 * (R54 @ np.asarray(p, float).T)).T + t54}
    # 5F pixels -> metres (image y points down, so flip it before the rotation fit)
    ids = sorted(pins)
    P = np.array([f5['dots'][k] for k in ids]) * [1, -1]
    Q = np.array([pins[k] for k in ids])
    s, R, t = similarity(P, Q)
    px2m = lambda p: (s * (R @ (np.atleast_2d(np.asarray(p, float)) * [1, -1]).T)).T + t
    to_m = {f: (lambda p, f=f: px2m(to5px[f](np.atleast_2d(p)))) for f in (5, 4)}
    pin_fit_err = {k: round(float(np.hypot(*(px2m(f5['dots'][k])[0] - pins[k]))), 2) for k in ids}

    # sketch positions in metres (places + bends); the inferred 4F disabled toilet uses the 5F offset
    sketch = {}
    for f in (5, 4):
        fl = tr['floors'][str(f)]
        sk = {k: to_m[f](v)[0] for k, v in {**fl['dots'], **fl['bends']}.items()}
        for node, base in INFERRED_DOT.get(f, {}).items():
            off = to_m[5](f5['dots']['male_disabled_toilet'])[0] - to_m[5](f5['dots']['exit5_door'])[0]
            sk[node] = sk[base] + off
        sketch[f] = sk

    # least squares, one floor at a time
    SIG_PIN, SIG_SKETCH = 0.25, 1.5
    sig_len = {'measured': lambda L: 0.3, 'steps': lambda L: max(0.5, 0.15 * L), 'guess': lambda L: 4.0}
    plan = {'about': 'WalkSense vector floor plan of CityU AC1 5F and 4F, built by map/make_floorplan.py. '
                     'Internal team data: metres, x east, y north. Read the "status" of every point and edge before trusting it.',
            'frame': {'units': 'm', 'x': 'east', 'y': 'north', 'north_deg': 0.0,
                      'origin': 'centroid of the 11 Google pins in phase2/map/coordinates.csv (phase2/map/build_map.py)',
                      'north_source': 'Google lat/long of 8 floor-5 places; the Google screenshot under the sketch is north-up '
                                      f'(fitted rotation {np.degrees(np.arctan2(R[1, 0], R[0, 0])):.1f} deg)'},
            'sources': {'sketch': tr['source'], 'graph': str(GRAPH.relative_to(REPO)), 'pins': str(PINS.relative_to(REPO))},
            'fit': {'m_per_screenshot_px': round(float(s), 4), 'sketch_vs_pins_m': pin_fit_err,
                    'sketch_vs_pins_rms_m': round(float(np.sqrt(np.mean(np.square(list(pin_fit_err.values()))))), 2),
                    'floor4_to_floor5_px': {'scale': round(float(s54), 4), 'rot_deg': round(float(np.degrees(np.arctan2(R54[1, 0], R54[0, 0]))), 2),
                                            'shift_px': [round(float(v), 1) for v in t54]},
                    'weights': {'pin_sigma_m': SIG_PIN, 'sketch_sigma_m': SIG_SKETCH, 'measured_sigma_m': 0.3,
                                'steps_sigma_m': 'max(0.5, 15% of length)', 'guess_sigma_m': 4.0}},
            'floors': {}}
    for f in (5, 4):
        fl = tr['floors'][str(f)]
        names = list(sketch[f])
        idx = {k: i for i, k in enumerate(names)}
        x0 = np.array([sketch[f][k] for k in names]).ravel()
        edges = []
        for path in PATHS[f]:
            a, b = path[0], path[-1]
            ga, gb = GRAPH_ID[f][a], GRAPH_ID[f][b]
            e = gedge.get((ga, gb)) or gedge.get((gb, ga))
            assert e is not None, (f, a, b)
            edges.append((path, e))
        assert len(edges) == sum(1 for e in graph['edges'] if e['floor_change'] == 0
                                 and e['from'] in GRAPH_ID[f].values()), f

        def res(x):
            X = x.reshape(-1, 2)
            r = [(X[idx[k]] - sketch[f][k]) / SIG_SKETCH for k in names]
            if f == 5:
                r += [(X[idx[k]] - np.array(pins[k])) / SIG_PIN for k in pins]
            for path, e in edges:
                L = poly_len([X[idx[k]] for k in path])
                r.append(np.array([(L - e['metres']) / sig_len[e['length_status']](e['metres'])]))
            return np.concatenate(r)

        sol = least_squares(res, x0)
        X = sol.x.reshape(-1, 2)
        pos = {k: X[idx[k]] for k in names}
        places = {}
        for k in REF[f].keys() | INFERRED_DOT.get(f, {}).keys():
            name, short = NAMES[f][k]
            inferred = k in INFERRED_DOT.get(f, {})
            st = ('measured pin (Google lat/long), adjusted by the fit' if k in pins and f == 5 else
                  'inferred: no dot on the sketch; 5F offset from Exit 5, at Google\'s wheelchair toilet' if inferred else
                  'sketch dot (Google screenshot scale), adjusted by the fit')
            places[k] = {'graph_id': GRAPH_ID[f][k], 'name': name, 'short': short, 'kind': KIND[k],
                         'x': round(float(pos[k][0]), 2), 'y': round(float(pos[k][1]), 2), 'status': st, 'inferred': inferred,
                         'sketch_xy': [round(float(v), 2) for v in sketch[f][k]],
                         'moved_by_fit_m': round(float(np.hypot(*(pos[k] - sketch[f][k]))), 2)}
            if k in LABEL_DIR.get(f, {}):
                places[k]['label_dx'], places[k]['label_dy'] = LABEL_DIR[f][k]
            if f == 5 and k in pins:
                places[k]['pin_xy'] = list(pins[k])
                places[k]['off_pin_m'] = round(float(np.hypot(*(pos[k] - np.array(pins[k])))), 2)
        bends = {k: [round(float(pos[k][0]), 2), round(float(pos[k][1]), 2)] for k in BENDS[f]}
        out_edges = []
        for path, e in edges:
            pts = [[round(float(pos[k][0]), 2), round(float(pos[k][1]), 2)] for k in path]
            drawn = poly_len(pts)
            a, b = path[0], path[-1]
            mark = MARKS[f].get((a, b)) or MARKS[f].get((b, a))
            out_edges.append({'from': a, 'to': b, 'via': list(path[1:-1]), 'points': pts, 'metres': e['metres'],
                              'source': e['length_status'], 'source_detail': e['length_source'], 'walk': e.get('walk'),
                              'steps': e.get('steps'), 'drawn_m': round(drawn, 2), 'residual_m': round(drawn - e['metres'], 2),
                              'sketch_mark_m': mark, 'note': NOT_IN_SKETCH.get((f, a, b), '')})
        # context: Google regions inside the box around the places, in metres
        pts = np.array([[p['x'], p['y']] for p in places.values()])
        box = [float(pts[:, 0].min() - MARGIN_M), float(pts[:, 1].min() - MARGIN_M),
               float(pts[:, 0].max() + MARGIN_M), float(pts[:, 1].max() + MARGIN_M)]
        rnd = lambda P: [[round(float(x), 2), round(float(y), 2)] for x, y in P]

        def to_poly(px_pts, hull=True):
            q = clip([tuple(v) for v in to_m[f](px_pts)], box)
            if len(q) < 3:
                return None
            if hull:                                         # nearly convex block: use its hull (drops text notches)
                h = _hull(q)
                if _area(h) < 1.3 * _area(q):
                    q = h
            return rnd(q)
        big = [box[0] - FOOT_MARGIN_M + MARGIN_M, box[1] - FOOT_MARGIN_M + MARGIN_M, box[2] + FOOT_MARGIN_M - MARGIN_M,
               box[3] + FOOT_MARGIN_M - MARGIN_M]
        comp_owner = {c: fp for fp, cs in fl['footprint_comps'].items() for c in cs}
        for reg in fl['regions']:                            # grow the view to show the named footprints
            if reg['comp'] in comp_owner and comp_owner[reg['comp']] != 'canteen':
                q = np.array(clip([tuple(v) for v in to_m[f](reg['pts'])], big) or [[box[0], box[1]]])
                box = [min(box[0], q[:, 0].min() - 1), min(box[1], q[:, 1].min() - 1),
                       max(box[2], q[:, 0].max() + 1), max(box[3], q[:, 1].max() + 1)]
        fp_meta = {fid: (label, kind, note) for fid, label, kind, _, note in FOOTPRINTS[f]}
        rooms, context = {}, []
        for reg in fl['regions']:
            poly = to_poly(reg['pts'])
            if poly is None:
                continue
            owner = comp_owner.get(reg['comp'])
            if owner:
                label, kind, note = fp_meta[owner]
                rooms.setdefault(owner, {'id': owner, 'place': owner if owner in places else None, 'label': label,
                                         'kind': kind, 'note': note, 'source': 'traced from the Google indoor map under the sketch',
                                         'polys': []})['polys'].append(poly)
            else:
                context.append({'kind': {'room': 'room', 'toilet': 'toilet', 'grey': 'core', 'light': 'service'}[reg['kind']],
                                'poly': poly})
        walkable = [p for p in (to_poly(w['pts'], hull=False) for w in fl['walkable']) if p]
        links = []
        for e in graph['edges']:
            if e['floor_change'] and (e['from'] in GRAPH_ID[f].values() or e['to'] in GRAPH_ID[f].values()):
                inv = {g: m for m, g in GRAPH_ID[f].items()}
                here = inv.get(e['from']) or inv.get(e['to'])
                other_f = 4 if f == 5 else 5
                inv_o = {g: m for m, g in GRAPH_ID[other_f].items()}
                there = inv_o.get(e['to']) if e['from'] in inv else inv_o.get(e['from'])
                leaves = e['from'] in inv
                links.append({'place': here, 'to_floor': other_f, 'to_place': there, 'mode': e['mode'],
                              'one_way': e['one_way'],
                              'direction': 'both' if not e['one_way'] else
                              ('down' if other_f < f else 'up') if leaves else ('up' if other_f < f else 'down'),
                              'leaves_here': leaves or not e['one_way'], 'seconds': e['seconds'],
                              'seconds_status': e['seconds_status'], 'seconds_source': e['seconds_source']})
        plan['floors'][str(f)] = {'bounds': [round(v, 2) for v in box], 'places': places, 'bends': bends,
                                  'edges': out_edges, 'links': links, 'rooms': list(rooms.values()),
                                  'walkable': walkable, 'context': context,
                                  'fit_cost': round(float(sol.cost), 3)}
        r = np.array([e['residual_m'] for e in out_edges])
        plan['fit'][f'edge_residual_rms_m_{f}F'] = round(float(np.sqrt(np.mean(r ** 2))), 2)
        print(f'{f}F: {len(places)} places, {len(out_edges)} edges, residual rms {np.sqrt(np.mean(r ** 2)):.2f} m, '
              f'{len(rooms)} footprints, {len(context)} context blocks, {len(walkable)} walkable polygons')
    # places.json pixels -> metres (affine, least squares) so old pixel positions can still be converted
    pj = json.loads((HERE / 'places.json').read_text())
    plan['px_to_m'] = {}
    for f in ('5', '4'):
        ks = [k for k in pj[f]['places'] if k in plan['floors'][f]['places']]
        A = np.array([[pj[f]['places'][k]['x'], pj[f]['places'][k]['y'], 1] for k in ks])
        B = np.array([[plan['floors'][f]['places'][k]['x'], plan['floors'][f]['places'][k]['y']] for k in ks])
        M, *_ = np.linalg.lstsq(A, B, rcond=None)
        err = np.hypot(*(A @ M - B).T)
        plan['px_to_m'][f] = {'matrix': [[round(float(v), 6) for v in row] for row in M.T],
                              'rms_m': round(float(np.sqrt(np.mean(err ** 2))), 2),
                              'about': 'x_m, y_m = matrix @ [px, py, 1] for places.json pixels (fallback only)'}
    OUT.write_text(json.dumps(plan, indent=1))
    print('wrote', OUT.relative_to(REPO))


if __name__ == '__main__':
    trace() if sys.argv[1:] == ['trace'] else build()
