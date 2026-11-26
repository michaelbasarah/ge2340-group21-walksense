"""Shared helpers for the 26-Nov morning session (Tian, iPhone17,4), stdlib only.

Same helpers and conventions as ../../2026-11-25-night/scripts/nightlib.py (recording metadata read from ZIP bytes, the
HH:MM:SS clock from the session day's midnight, the 25-Nov node names and display names), with this session's day, run
window and labels file. Nothing here executes or imports anything from a ZIP; ZIPs are read as bytes.
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # phase2/clean-data/2026-11-26-tian
RAW = ROOT / 'raw'
LABELS = ROOT / 'labels_tian26.csv'
NIGHT_SCRIPTS = ROOT.parent / '2026-11-25-night' / 'scripts'
NAMES = ROOT.parent.parent / 'new' / 'day3' / 'names_25night.csv'     # night node names -> graph-v2 places (same nodes)
HK = timezone(timedelta(hours=8))
DAY = datetime(2026, 11, 26, tzinfo=HK)
WINDOW = (DAY + timedelta(hours=9), DAY + timedelta(hours=11))     # Tian's morning run: 09:30 to 10:39
TRACK = 'tian26'
SLOT = 'iphone'          # phone folder in the clean tree, as in Tian's night tree (../2026-11-25-night/tian/clean)
DEVICE = 'iPhone17,4'    # Tian's iPhone 16 (day3 config.json phones: ip16)

LABEL_FIELDS = ['source_zip', 'sha256', 'chat_time', 'chat_gap_s', 'tian_caption', 'device', 'slot', 'track', 'start_hk',
                'start_iso', 'duration_s', 'kind', 'floor', 'no', 'node', 'from_node', 'to_node', 'place_v2', 'status',
                'confidence', 'reason', 'pressure_hpa']

sys.path.insert(0, str(NIGHT_SCRIPTS))
from nightlib import PLACE, PLACE_4F, STOP_MIN_S, read_meta, place_label   # noqa: E402,F401  (same nodes and names)


def clock(epoch: float) -> str:
    s = int(round(epoch - DAY.timestamp()))
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, HK).strftime('%Y-%m-%d %H:%M:%S')


def clock_epoch(hk: str) -> float:
    h, m, s = (int(x) for x in hk.split(':'))
    return DAY.timestamp() + h * 3600 + m * 60 + s


def kind_of(dur: float) -> str:
    return 'stop' if dur >= STOP_MIN_S else 'walk'


def read_labels() -> list[dict]:
    with LABELS.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write_labels(rows: list[dict]) -> None:
    with LABELS.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, '') for k in LABEL_FIELDS} for r in rows)


def zip_ok(b: bytes) -> bool:
    try:
        zipfile.ZipFile(io.BytesIO(b))
        return True
    except zipfile.BadZipFile:
        return False
