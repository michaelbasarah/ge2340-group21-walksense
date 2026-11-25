#!/usr/bin/env python3
"""Floor images + circle positions for the upload page, from the collector's sketch.

Source: phase2/clean-data/2026-11-24/floor-sketch-v1.pdf (page 1 = 5F, page 2 = 4F; red dots = stops).
Writes floor5.png, floor4.png and places.json (pixel position of every place on its floor image).
Needs pymupdf + pillow + numpy (only to rebuild; the page uses the committed outputs).

Which dot is which place (25-Nov, entry 25 of PROCESS-LOG):
- 5F: order and metre marks of the 24-Nov route, checked against the team's floor-5 pins
  (phase2/map/coordinates_meters.csv: Exit 5 / male toilet / Y5-302 south-west, Exit 10 / female
  toilet north-east). Escalator up vs down from the headings of the three escalator walks
  (6 of 6 recordings agree: down = the south dot).
- 4F: the 9-dot loop + the escalator/Y4502 triangle match the 24-Nov walks; the lift landing sits
  under the 5F lift. The 4F disabled toilet has NO dot: placed at the 5F offset between Exit 5 and
  the male disabled toilet (marked inferred).
"""
import json
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

HERE = Path(__file__).resolve().parent
PDF = HERE.parents[2] / 'clean-data' / '2026-11-24' / 'floor-sketch-v1.pdf'
DPI, OUT_W, MARGIN = 144, 760, 150
# Approximate dot positions read off the sketch (1440 x 810 page units); each must match one red dot.
REF = {5: {'canteen': (328, 282), 'exit5_door': (228, 376), 'male_toilet': (277, 412), 'y5302': (368, 502),
           'sr9': (486, 420), 'y5202': (563, 304), 'female_toilet': (468, 214), 'exit10_door': (430, 181),
           'esca_up': (390, 294), 'esca_down': (354, 333), 'male_disabled_toilet': (210, 394),
           'lift_stairs5': (170, 472), 'y5401': (203, 516), 'y5302_point2': (282, 592)},
       4: {'lift_stairs5': (172, 512), 'exit5_door': (230, 412), 'lt2a': (298, 414), 'lt2b': (437, 554),
           'esca_down': (466, 474), 'y4502': (572, 516), 'esca_up': (527, 417), 'lt1b': (602, 376),
           'lt1a': (466, 243), 'exit10_door': (449, 184), 'gate': (350, 289)}}
INFERRED = {4: {'disabled_toilet': (230 - 18, 412 + 18)}}   # 5F male_disabled_toilet - exit5_door offset


def red_dots(img):
    red = (img[:, :, 0] > 220) & (img[:, :, 1] < 90) & (img[:, :, 2] < 90)
    seen, dots = np.zeros_like(red), []
    for y, x in zip(*np.nonzero(red)):
        if seen[y, x]:
            continue
        stack, comp = [(y, x)], []
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            comp.append((cy, cx))
            for ny in (cy - 1, cy, cy + 1):
                for nx in (cx - 1, cx, cx + 1):
                    if 0 <= ny < red.shape[0] and 0 <= nx < red.shape[1] and red[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if len(comp) > 200:                       # a dot is ~590 px at 144 dpi; skips stray red text
            c = np.array(comp)
            dots.append((c[:, 1].mean(), c[:, 0].mean()))
    return dots


def main():
    doc, places = pymupdf.open(PDF), {}
    for page, floor in zip(doc, (5, 4)):
        pix = page.get_pixmap(dpi=DPI)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
        k = pix.w / page.rect.width                  # page units -> pixels
        dots = red_dots(img)
        assert len(dots) == len(REF[floor]), (floor, len(dots))
        pos = {}
        for node, (rx, ry) in REF[floor].items():
            d = min(dots, key=lambda p: (p[0] - rx * k) ** 2 + (p[1] - ry * k) ** 2)
            assert ((d[0] - rx * k) ** 2 + (d[1] - ry * k) ** 2) ** 0.5 < 15 * k, (floor, node)
            pos[node] = d
        assert len({pos[n] for n in pos}) == len(pos), 'two places matched one dot'
        for node, (rx, ry) in INFERRED.get(floor, {}).items():
            pos[node] = (rx * k, ry * k)
        xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
        x0, y0 = max(0, int(min(xs)) - MARGIN), max(0, int(min(ys)) - MARGIN)
        x1, y1 = min(pix.w, int(max(xs)) + MARGIN), min(pix.h, int(max(ys)) + MARGIN)
        s = OUT_W / (x1 - x0)
        out = Image.fromarray(np.ascontiguousarray(img[y0:y1, x0:x1])).resize((OUT_W, round((y1 - y0) * s)), Image.LANCZOS)
        out.save(HERE / f'floor{floor}.png', optimize=True)
        places[floor] = {'image': f'floor{floor}.png', 'width': out.width, 'height': out.height,
                         'places': {n: {'x': round((p[0] - x0) * s, 1), 'y': round((p[1] - y0) * s, 1),
                                        'inferred': n in INFERRED.get(floor, {})} for n, p in pos.items()}}
        print(f'{floor}F: {len(pos)} places, image {out.width}x{out.height}')
    (HERE / 'places.json').write_text(json.dumps(places, indent=1))


if __name__ == '__main__':
    main()
