"""Generate a reader-friendly ROUTE.html from a clean-data folder's manifest.csv.
Usage: python make_route_html.py "<folder>"  (leaves ROUTE.md / README untouched)
"""
import csv, os, sys, json
from collections import defaultdict

OUT = sys.argv[1]
man = list(csv.DictReader(open(os.path.join(OUT, 'manifest.csv'), encoding='utf-8')))
sess = 'Session ' + (os.path.basename(OUT).split('sesi')[-1] or '?')
try:
    summ = json.load(open(os.path.join(OUT, 'summary.json'), encoding='utf-8'))
except Exception:
    summ = {}

order = []
byfolder = defaultdict(list)
for r in man:
    if r['folder'] not in byfolder:
        order.append(r['folder'])
    byfolder[r['folder']].append(r)
phones = sorted(set(r['phone'] for r in man))
floors = list(dict.fromkeys(r['floor'] for r in man))  # order of first appearance (floor 5 then 4)


def esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


h = ['<!doctype html><meta charset="utf-8"><title>WalkSense route — 24 Nov %s</title>' % sess,
     '<style>body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:720px;margin:24px auto;'
     'padding:0 16px;color:#1b2430;line-height:1.5}h1{font-size:22px}h2{margin-top:28px;border-bottom:2px solid #e4e8ee;'
     'padding-bottom:6px}.stop{background:#eef4ff;border-left:4px solid #2f6feb;padding:8px 12px;margin:8px 0;border-radius:6px}'
     '.walk{color:#5a6472;padding:2px 0 2px 20px;font-size:14px}.walk:before{content:"\\2193 walk ";color:#9aa4b2}'
     '.t{color:#9aa4b2;font-size:12px;font-variant-numeric:tabular-nums;margin-right:8px}'
     '.ph{float:right;font-size:12px;color:#2f6feb;background:#fff;border:1px solid #cdd9f0;border-radius:10px;padding:0 8px}'
     '.n{color:#5a6472;font-size:13px}.fc{background:#fff6e5;border-left:4px solid #e8a33d;padding:8px 12px;'
     'margin:8px 0;border-radius:6px;font-size:14px}</style>']
h.append(f'<h1>WalkSense route — 24 Nov 2026, {sess}</h1>')
h.append(f'<p class=n>{len(phones)} phones ({", ".join(phones)}) walked together. '
         '<b style="color:#2f6feb">Blue = stop</b> (~60 s, phone faces the door). Grey = walk between stops.</p>')
for fl in floors:
    h.append(f'<h2>Floor {fl}</h2>')
    for f in [x for x in order if x.startswith(f'floor{fl}/')]:
        rows = byfolder[f]; r0 = rows[0]; t = min(x['start_hk'] for x in rows)
        nph = len(set(x['phone'] for x in rows))
        if r0['type'] == 'stop':
            h.append(f'<div class=stop><span class=t>{t}</span><b>{esc(r0["place"])}</b>'
                     f'<span class=ph>{nph} phone{"s" if nph > 1 else ""}</span></div>')
        else:
            h.append(f'<div class=walk><span class=t>{t}</span>{esc(r0["from_node"])} '
                     f'&rarr; {esc(r0["to_node"])}</div>')
    if fl == floors[0] and len(floors) > 1:
        h.append('<div class=fc>&#8595; took the lift / stairs <b>down to floor 4</b> '
                 '(floor change — no walk recorded)</div>')
open(os.path.join(OUT, 'ROUTE.html'), 'w', encoding='utf-8').write('\n'.join(h) + '\n')
print('wrote', os.path.join(OUT, 'ROUTE.html'), '|', len(phones), 'phones:', phones, '| floors', floors)
