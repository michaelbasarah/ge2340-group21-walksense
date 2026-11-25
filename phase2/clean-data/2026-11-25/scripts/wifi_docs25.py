import gzip, csv, os, json, io
from datetime import datetime, timezone, timedelta

_BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA=os.path.join(_BASE,"raw")
OUT =os.path.join(_BASE,"clean")
UTC=timezone.utc; HK=timezone(timedelta(hours=8))
slots=json.load(open(os.path.join(OUT,"_slots.json")))

INFRA_KEYS=["ifl","eduroam","cityu wlan","hk tech 300","cityu alumni","cityu collaboration",
            "wi-fi.hk via cityu","csl"]
def is_infra(ssid):
    s=(ssid or "").lower()
    return any(k in s for k in INFRA_KEYS)

# stop windows (anchor .. anchor+dur). Use 60s dwell.
stop_slots=[s for s in slots if s["kind"]=="stop"]
# anchor stored as unix float
for s in stop_slots: s["a"]=float(s["anchor"])

# ---- parse wigle logs ----
logs=[f for f in os.listdir(DATA) if f.startswith("WigleWifi") and f.endswith(".csv.gz")]
log_rows=[]; obs=[]; empty=[]
for lg in sorted(logs):
    rows=list(csv.reader(gzip.open(os.path.join(DATA,lg),"rt",encoding="utf-8",errors="replace")))
    data=rows[2:] if len(rows)>2 else []
    wifi=[r for r in data if len(r)>=14 and r[13]=="WIFI"]
    log_rows.append((lg,len(data),len(wifi)))
    if not wifi: empty.append(lg)
    for r in wifi:
        mac,ssid,auth,fs=r[0],r[1],r[2],r[3]
        try: rssi=float(r[6])
        except: rssi=""
        # FirstSeen is UTC
        t=datetime.strptime(fs,"%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        obs.append(dict(mac=mac,ssid=ssid,rssi=rssi,ts=t.timestamp(),
                        fs_hk=t.astimezone(HK).isoformat(),infra=is_infra(ssid)))

uniq_bssid=len(set(o["mac"] for o in obs))
# ---- associate each obs to nearest stop ----
assoc=[]
for o in obs:
    best=None;bd=1e9
    for s in stop_slots:
        # distance to the window [a, a+60]
        if o["ts"]<s["a"]: d=s["a"]-o["ts"]
        elif o["ts"]>s["a"]+60: d=o["ts"]-(s["a"]+60)
        else: d=0.0
        if d<bd: bd=d;best=s
    if best is None: continue
    if bd==0: at="in_window"
    elif bd<=120: at="approach"
    else: continue
    assoc.append((o,best,bd,at))

# ---- write wifi files ----
wd=os.path.join(OUT,"wifi"); os.makedirs(wd,exist_ok=True)
assoc.sort(key=lambda x:(x[1]["floor"],x[1]["no"],x[2]))
with open(os.path.join(wd,"stop_associations.csv"),"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["wifi_id","floor","stop_no","node","assoc_type","time_gap_s","scanner_phone","bssid","ssid","rssi","is_cityu_infra","firstseen_hk"])
    for i,(o,s,d,at) in enumerate(assoc,1):
        w.writerow([f"W{i:05d}",s["floor"],s["no"],s["node"],at,round(d,1),"a56",o["mac"],o["ssid"],o["rssi"],o["infra"],o["fs_hk"]])
with open(os.path.join(wd,"observations.csv"),"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["bssid","ssid","rssi","is_cityu_infra","firstseen_hk"])
    for o in sorted(obs,key=lambda o:o["ts"]):
        w.writerow([o["mac"],o["ssid"],o["rssi"],o["infra"],o["fs_hk"]])
# coverage
from collections import defaultdict
cov=defaultdict(lambda:[0,0,set()])
for o,s,d,at in assoc:
    key=(s["floor"],s["no"],s["node"])
    if at=="in_window": cov[key][0]+=1
    else: cov[key][1]+=1
    cov[key][2].add(o["mac"])
with open(os.path.join(wd,"stop_coverage.csv"),"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["floor","stop_no","node","wifi_in_window","wifi_approach","unique_bssids"])
    for s in stop_slots:
        key=(s["floor"],s["no"],s["node"]); c=cov.get(key,[0,0,set()])
        w.writerow([s["floor"],s["no"],s["node"],c[0],c[1],len(c[2])])
with open(os.path.join(wd,"log_summary.csv"),"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["log","rows","wifi_rows","empty"])
    for lg,n,nw in log_rows: w.writerow([lg,n,nw,nw==0])

stops_cov=sum(1 for s in stop_slots if cov.get((s["floor"],s["no"],s["node"]),[0,0,set()])[0]+cov.get((s["floor"],s["no"],s["node"]),[0,0,set()])[1]>0)
inw=sum(1 for *_ ,at in [(a[3],) for a in assoc] for at in [_[0]]) if False else sum(1 for a in assoc if a[3]=="in_window")
app=sum(1 for a in assoc if a[3]=="approach")
infra_obs=sum(1 for o in obs if o["infra"])
wifi_stats=dict(logs=len(log_rows),empty_logs=empty,source_rows=sum(n for _,n,_ in log_rows),
    wifi_clean=len(obs),unique_bssids=uniq_bssid,associations=len(assoc),
    in_window=inw,approach=app,stops_with_wifi=stops_cov,stops_total=len(stop_slots),infra_obs=infra_obs)
print("wifi:",json.dumps(wifi_stats,indent=1))

# ---- summary.json ----
import glob
nrec=sum(1 for s in slots for _ in s["members"])
summary=dict(dataset="2026-11-25 (floor 5 + floor 4)",
  phones=["a55","a56","iphone"],
  recordings_raw=164, recordings_unique=162, recordings_written=nrec,
  stops=sum(1 for s in slots if s["kind"]=="stop"),
  walks=sum(1 for s in slots if s["kind"]=="walk"),
  stops_floor5=sum(1 for s in slots if s["kind"]=="stop" and s["floor"]==5),
  stops_floor4=sum(1 for s in slots if s["kind"]=="stop" and s["floor"]==4),
  walks_floor5=sum(1 for s in slots if s["kind"]=="walk" and s["floor"]==5),
  walks_floor4=sum(1 for s in slots if s["kind"]=="walk" and s["floor"]==4),
  wifi=wifi_stats,
  warnings=[
    "Only ONE floor/barometer sensor this session (iphone, iPhone19,2) - no s24, no cross-phone floor redundancy. iPhone barometer verified clean (~0.005 hPa within-stop std; +0.9 hPa floor-5->floor-4 step).",
    "a56 missing 1 recording: floor4 w06 esca_down->y4502 (walk) - covered by iphone+a55. (The a56 y5202 stop was uploaded later and added.)",
    "2 byte-identical a55 duplicates dropped (sr9->y5202 walk, gate stop). 1 a56 double-take of exit5_door->lt2a walk: kept the in-lockstep take.",
    "y5302 visited twice = two different doors (y5302 + y5302_point2), not a revisit. No canteen revisit stop this session.",
  ])
json.dump(summary,open(os.path.join(OUT,"summary.json"),"w"),indent=2)
print("summary written")
