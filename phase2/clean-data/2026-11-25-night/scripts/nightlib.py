"""Shared helpers for the 25-Nov night run folder (stdlib only): recording metadata, clock, labels CSV, name check.

Used by build_night.py (raw/ + labels_night.csv -> clean/) and ingest_export.py (a WhatsApp export -> new raw ZIPs +
proposed rows in labels_night.csv). Nothing here executes or imports anything from a ZIP; ZIPs are read as bytes.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # phase2/clean-data/2026-11-25-night
RAW = ROOT / 'raw'
OUT = ROOT / 'clean'
LABELS = ROOT / 'labels_night.csv'
WIFI_LOGS = ROOT / 'wifi_logs.csv'           # WiGLE log -> track, scanner phone (one row per log in raw/)
# Tracks = the groups that walked together. Each track is its own clean tree <ROOT>/<track>/clean and its own day-3
# session: 'round' = Dicta (iPhone19,2) + Chris (SM-A566B) in lockstep, 'tian' = Tian (iPhone17,4) on his own pass.
HK = timezone(timedelta(hours=8))
DAY = datetime(2026, 11, 25, tzinfo=HK)                 # session day; times after midnight are written as 24:mm:ss
WINDOW = (DAY + timedelta(hours=21), DAY + timedelta(hours=25, minutes=30))   # the night run: 25 Nov 21:00 -> 26 Nov 01:30
ANCHOR_MODEL = 'iPhone19,2'      # Dicta's iPhone: her complete, named sequence defines the route slots
# phone folder ("slot") per device model. iphone = Dicta's iPhone19,2 as in her 25-Nov tree; the others use the day-3 handset id
SLOT = {'iPhone19,2': 'iphone', 'iPhone17,4': 'ip16', 'SM-S9280': 's24', 'SM-A556E': 'a55', 'SM-A566B': 'a56'}
STOP_MIN_S = 40.0                # as build25.py: >= 40 s = stop, shorter = walk
MATCH_S = 150.0                  # as build25.py: another phone's recording joins the nearest same-type slot within 150 s

LABEL_FIELDS = ['source_zip', 'label_raw', 'device', 'slot', 'track', 'anchor', 'start_hk', 'start_iso', 'duration_s', 'type',
                'floor', 'no', 'node', 'from_node', 'to_node', 'status', 'confidence', 'reason', 'pressure_hpa', 'sha256']

# display names, identical to Dicta's 25-Nov tree (build25.py ROUTE) so the app's place labels do not change
PLACE = {'canteen': 'Canteen', 'exit5_door': 'Exit 5 door', 'male_toilet': 'Male toilet', 'y5302': 'Y5302',
         'sr9': 'SR9 (study rooms)', 'y5202': 'Y5202', 'female_toilet': 'Female toilet', 'exit10_door': 'Exit 10 door',
         'esca_up': 'Escalator up', 'esca_down': 'Escalator down', 'male_disabled_toilet': 'Male disabled toilet',
         'lift_stairs5': 'Lift / stairs 5', 'y5401': 'Y5401', 'y5302_point2': 'Y5302 (point 2 - other door)',
         'disabled_toilet': 'Disabled toilet', 'lt2a': 'LT2A', 'lt2b': 'LT2B', 'y4502': 'Y4502', 'lt1b': 'LT1B',
         'lt1a': 'LT1A', 'gate': 'Gate (building entrance/exit)'}
PLACE_4F = {'lift_stairs5': 'Lift / stairs 5 (floor-4 landing)'}


def place_label(floor: int, node: str) -> str:
    return (PLACE_4F if int(floor) == 4 else {}).get(node, PLACE.get(node, node))


def read_meta(b: bytes) -> dict | None:
    """A phyphox ZIP (bytes) -> device model, START epoch, duration, sensor CSV bytes, mean pressure. None if not phyphox."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(b))
    except zipfile.BadZipFile:
        return None
    names = zf.namelist()
    if not any(n.endswith('meta/device.csv') for n in names):
        return None
    dev, start, dur, sensors = '', None, 0.0, {}
    for n in names:
        if n.endswith('meta/device.csv'):
            for row in csv.reader(io.StringIO(zf.read(n).decode('utf-8', 'replace'))):
                if len(row) >= 2 and row[0] == 'deviceModel':
                    dev = row[1]
        elif n.endswith('meta/time.csv'):
            for row in list(csv.reader(io.StringIO(zf.read(n).decode('utf-8', 'replace'))))[1:]:
                if len(row) >= 3 and row[0].upper() == 'START':
                    start = float(row[2])
                if len(row) >= 2 and row[0].upper() in ('PAUSE', 'STOP', 'END'):
                    try:
                        dur = float(row[1])
                    except ValueError:
                        pass
        elif n.endswith('.csv') and 'meta/' not in n:
            sensors[Path(n).name] = zf.read(n)
    if start is None:
        return None
    return {'device': dev, 'start': start, 'dur': dur, 'sensors': sensors, 'pressure': mean_pressure(sensors)}


def mean_pressure(sensors: dict):
    for fn in ('Barometer.csv', 'Pressure.csv'):
        if fn in sensors:
            rows = list(csv.reader(io.StringIO(sensors[fn].decode('utf-8', 'replace'))))[1:]
            v = [float(r[1]) for r in rows if len(r) >= 2 and r[1]]
            return round(sum(v) / len(v), 2) if v else ''
    return ''


def clock(epoch: float) -> str:
    """HH:MM:SS from the session day's midnight (HK). After midnight the hour goes on: 00:16 on 26 Nov = 24:16:00.
    Every reader of start_hk (day3 data.py, upload walksense.hk_epoch) turns it into day + h:m:s, so this keeps the
    order and gaps right across midnight without code changes."""
    s = int(round(epoch - DAY.timestamp()))
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, HK).strftime('%Y-%m-%d %H:%M:%S')


def clock_epoch(hk: str) -> float:
    h, m, s = (int(x) for x in hk.split(':'))
    return DAY.timestamp() + h * 3600 + m * 60 + s


def strip_prefix(name: str) -> str:
    """WhatsApp iOS export prefix '00001999-' removed (Dicta's raw folders keep the phyphox name only)."""
    return re.sub(r'^\d{8}-', '', name)


def label_of(name: str) -> str:
    return re.sub(r'\s+\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}(\s*\(\d+\))?\.zip$', '', strip_prefix(name), flags=re.I).strip()


def plain_name(name: str) -> str:
    """Name without a browser's duplicate-download suffix: 'x 2026-11-25 22-07-45 (1).zip' -> 'x 2026-11-25 22-07-45.zip'."""
    return re.sub(r'\s*\(\d+\)(\.zip)$', r'\1', name, flags=re.I)


def kind_of(dur: float) -> str:
    return 'stop' if dur >= STOP_MIN_S else 'walk'


def read_labels() -> list[dict]:
    if not LABELS.exists():
        return []
    with LABELS.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write_labels(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: (r.get('track', ''), clock_epoch(r['start_hk']), r['slot']))
    with LABELS.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, '') for k in LABEL_FIELDS} for r in rows)


# ----------------------------------------------------------------------------- name check (for teammates' imports)
# The team's file names mix English and Indonesian (lt/lv/lantai N = floor N, turun = down, naik = up, ke/to = to,
# disb/disable = disabled, cewe = female, cowo = male, ext = exit, kantin = canteen). Each pattern is replaced by a
# token, in this order, so later patterns cannot reuse the same characters. Used only to CHECK a time-matched slot.
_FLOOR = r'\b(lt|lv|lvl|level|lantai|floor|f)\s*[45]\b|\b[45]\s*f\b'
_ALIAS = [
    ('disabled', r'\b(male\s+)?((toilet|tolet|tlt|toil\w*)\s+)?(disb|disab\w*|disable\w*|sisb)(\s+(toilet|tolet|tlt|toil\w*))?(\s+(cowo|cwo|male|men|mix\w*))?\b'),
    ('female_toilet', r'\b(toilet|tolet|tlt|toil\w*)\s+(cewe\w*|cwe\w*|female|women)\b|\b(female|women|girl)(\s+(toilet|tolet|tlt))?\b'),
    ('male_toilet', r'\b(toilet|tolet|tlt|toil\w*)\s+(cowo\w*|cwo\w*|male|men\w*)\b|\b(male|men|mens|boy)(\s+(toilet|tolet|tlt))?\b'),
    ('exit10_door', r'\b(exit|ext|ex|ezit)\s*10\b(\s+door)?'),
    ('exit5_door', r'\b(exit|ext|ex|ezit)\s*5\b(\s+door)?'),
    ('esca_up', r'\b(esca\w*|eska\w*|eaca\w*|escalator)\s+(up|naik)\b'),
    ('esca_down', r'\b(esca\w*|eska\w*|eaca\w*|escalator)\s+(down|turun)\b'),
    ('y5302', r'\by\s*5302(\s+(back|point\s*2|p2|belakang))?\b'),
    ('sr9', r'\bsr\s*9\b|\bstudy\s*rooms?\b'),
    ('lift_stairs5', r'\b(lift|stairs?|tangga)(\s*(lift|stairs?|5))*\b'),
    ('canteen', r'\b(canteen|kantin|kntin|cantin)\b'),
    ('gate', r'\b(gate|entrance|pintu)\b'),
] + [(r, rf'\b{r}\b') for r in ('y5202', 'y5401', 'y4502', 'lt1a', 'lt1b', 'lt2a', 'lt2b')]
# token -> nodes it agrees with (y5302 alone may be either door; "disabled" is the 5F male or the 4F mixed one)
_AGREES = {'y5302': {'y5302', 'y5302_point2'}, 'disabled': {'male_disabled_toilet', 'disabled_toilet'}}


def _tokens(text: str) -> list[str]:
    t = re.sub(_FLOOR, ' ', text.lower())
    found = []
    for tok, pat in _ALIAS:
        for m in list(re.finditer(pat, t)):
            found.append((m.start(), tok))
        t = re.sub(pat, lambda m: ' ' * len(m.group(0)), t)
    return [tok for _, tok in sorted(found)]


def name_nodes(label: str, kind: str) -> list[str] | None:
    """Place tokens read from a file label: [node] for a stop, [from, to] for a walk; None if it cannot be read."""
    if kind == 'walk':
        parts = re.split(r'\s+(?:ke|to|->|-)\s+', label.lower(), maxsplit=1)
        if len(parts) != 2:                      # Tian's style: 'y5302 sr9' = from y5302 to sr9 (two places, no 'to')
            t = _tokens(label)
            return t if len(t) == 2 else None
        a, b = _tokens(parts[0]), _tokens(parts[1])
        return [a[0], b[0]] if len(a) == 1 and len(b) == 1 else None
    t = _tokens(label)
    return t if len(t) == 1 else None


def agrees(tokens: list[str] | None, nodes: list[str]) -> bool:
    return tokens is not None and len(tokens) == len(nodes) and all(
        n in _AGREES.get(t, {t}) for t, n in zip(tokens, nodes))
