import zipfile, io, os, csv, json, shutil, re
from datetime import datetime, timezone, timedelta
from collections import defaultdict

_BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA=os.path.join(_BASE,"raw")
OUT =os.path.join(_BASE,"clean")
HK = timezone(timedelta(hours=8))
DEV = {"SM-A556E":"a55","SM-A566B":"a56","iPhone19,2":"iphone"}

# ---- load every recording's bytes + meta ----
def load_all():
    out=[]
    def handle(data, label, source):
        zf=zipfile.ZipFile(io.BytesIO(data))
        names=zf.namelist()
        dev=""; start=None; dur=None
        for n in names:
            if n.endswith("meta/device.csv"):
                for row in csv.reader(io.StringIO(zf.read(n).decode("utf-8","replace"))):
                    if len(row)>=2 and row[0]=="deviceModel": dev=row[1]
            elif n.endswith("meta/time.csv"):
                for row in list(csv.reader(io.StringIO(zf.read(n).decode("utf-8","replace"))))[1:]:
                    if len(row)>=3 and row[0].upper()=="START": start=float(row[2])
                    if len(row)>=2 and row[0].upper() in ("PAUSE","STOP","END"):
                        try: dur=float(row[1])
                        except: pass
        sensors={}
        for n in names:
            b=os.path.basename(n)
            if b.endswith(".csv") and "meta/" not in n:
                sensors[b]=zf.read(n)
        out.append(dict(dev=DEV.get(dev,dev),start=start,dur=dur or 0,
                        label=label,source=source,sensors=sensors))
    for fn in sorted(os.listdir(DATA)):
        if not fn.lower().endswith(".zip"): continue
        p=os.path.join(DATA,fn)
        if fn=="attachments.zip":
            with zipfile.ZipFile(p) as o:
                for inner in o.namelist():
                    if inner.lower().endswith(".zip"): handle(o.read(inner), inner, "attachments")
        else:
            with open(p,"rb") as f: handle(f.read(), fn, "toplevel")
    return out

recs=load_all()
print("loaded",len(recs),"recordings")

# ---- ROUTE (from iphone canonical sequence) ----
# each slot: (floor, kind, no, node_or_fromto, place)
ROUTE=[
 (5,"stop","s01","canteen","Canteen"),
 (5,"walk","w01",("canteen","exit5_door"),None),
 (5,"stop","s02","exit5_door","Exit 5 door"),
 (5,"walk","w02",("exit5_door","male_toilet"),None),
 (5,"stop","s03","male_toilet","Male toilet"),
 (5,"walk","w03",("male_toilet","y5302"),None),
 (5,"stop","s04","y5302","Y5302"),
 (5,"walk","w04",("y5302","sr9"),None),
 (5,"stop","s05","sr9","SR9 (study rooms)"),
 (5,"walk","w05",("sr9","y5202"),None),
 (5,"stop","s06","y5202","Y5202"),
 (5,"walk","w06",("y5202","female_toilet"),None),
 (5,"stop","s07","female_toilet","Female toilet"),
 (5,"walk","w07",("female_toilet","exit10_door"),None),
 (5,"stop","s08","exit10_door","Exit 10 door"),
 (5,"walk","w08",("exit10_door","canteen"),None),
 (5,"stop","s09","esca_up","Escalator up"),
 (5,"walk","w09",("esca_up","canteen"),None),
 (5,"walk","w10",("canteen","esca_down"),None),
 (5,"stop","s10","esca_down","Escalator down"),
 (5,"walk","w11",("esca_up","esca_down"),None),
 (5,"walk","w12",("exit5_door","male_disabled_toilet"),None),
 (5,"stop","s11","male_disabled_toilet","Male disabled toilet"),
 (5,"walk","w13",("male_disabled_toilet","lift_stairs5"),None),
 (5,"stop","s12","lift_stairs5","Lift / stairs 5"),
 (5,"walk","w14",("lift_stairs5","y5401"),None),
 (5,"stop","s13","y5401","Y5401"),
 (5,"walk","w15",("y5401","y5302_point2"),None),
 (5,"stop","s14","y5302_point2","Y5302 (point 2 - other door)"),
 (4,"stop","s01","lift_stairs5","Lift / stairs 5 (floor-4 landing)"),
 (4,"walk","w01",("lift_stairs5","disabled_toilet"),None),
 (4,"stop","s02","disabled_toilet","Disabled toilet"),
 (4,"walk","w02",("disabled_toilet","exit5_door"),None),
 (4,"stop","s03","exit5_door","Exit 5 door"),
 (4,"walk","w03",("exit5_door","lt2a"),None),
 (4,"stop","s04","lt2a","LT2A"),
 (4,"walk","w04",("lt2a","lt2b"),None),
 (4,"stop","s05","lt2b","LT2B"),
 (4,"walk","w05",("lt2b","esca_down"),None),
 (4,"stop","s06","esca_down","Escalator down"),
 (4,"walk","w06",("esca_down","y4502"),None),
 (4,"stop","s07","y4502","Y4502"),
 (4,"walk","w07",("y4502","esca_up"),None),
 (4,"stop","s08","esca_up","Escalator up"),
 (4,"walk","w08",("esca_up","lt1b"),None),
 (4,"stop","s09","lt1b","LT1B"),
 (4,"walk","w09",("lt1b","lt1a"),None),
 (4,"stop","s10","lt1a","LT1A"),
 (4,"walk","w10",("lt1a","exit10_door"),None),
 (4,"stop","s11","exit10_door","Exit 10 door"),
 (4,"walk","w11",("exit10_door","gate"),None),
 (4,"stop","s12","gate","Gate (building entrance/exit)"),
 (4,"walk","w12",("gate","exit5_door"),None),
 (4,"walk","w13",("esca_down","esca_up"),None),
]

# anchor each slot to the iphone recording (iphone is complete, in order)
iph=sorted([r for r in recs if r["dev"]=="iphone"], key=lambda r:r["start"])
assert len(iph)==len(ROUTE), f"iph {len(iph)} != route {len(ROUTE)}"

slots=[]
for slot,ir in zip(ROUTE,iph):
    floor,kind,no,nd,place=slot
    want = "stop" if ir["dur"]>=40 else "walk"
    assert kind==want, f"kind mismatch {no} {kind} vs {want} ({ir['label']})"
    slots.append(dict(floor=floor,kind=kind,no=no,node=nd,place=place,anchor=ir["start"],members={}))

# assign a55/a56 by nearest anchor, same kind, not already taken
for ph in ("a55","a56"):
    prs=sorted([r for r in recs if r["dev"]==ph], key=lambda r:r["start"])
    for r in prs:
        rk = "stop" if r["dur"]>=40 else "walk"
        best=None;bd=1e9
        for s in slots:
            if s["kind"]!=rk: continue
            d=abs(r["start"]-s["anchor"])
            if d<bd: bd=d;best=s
        if best is None or bd>150:
            print("  UNASSIGNED",ph,r["label"],bd); continue
        if ph in best["members"]:
            # duplicate contention: keep the nearer one
            cur=best["members"][ph]
            if abs(cur["start"]-best["anchor"])<=bd:
                continue  # existing is closer, drop this
        best["members"][ph]=r
# add iphone members
for s,ir in zip(slots,iph):
    s["members"]["iphone"]=ir

# ---- write tree ----
if os.path.exists(OUT): shutil.rmtree(OUT)
SENS_ORDER=["Accelerometer.csv","Barometer.csv","Gyroscope.csv","Magnetometer.csv"]
manifest=[]
def row_count(b): return max(0,b.count(b"\n")-1)
def baro_mean(sensors):
    if "Barometer.csv" not in sensors: return ""
    rows=list(csv.reader(io.StringIO(sensors["Barometer.csv"].decode())))[1:]
    v=[float(x[1]) for x in rows if len(x)>=2 and x[1]]
    return round(sum(v)/len(v),2) if v else ""

for s in slots:
    floor=s["floor"];
    if s["kind"]=="stop":
        folder=f"floor{floor}/stops/{s['no']}_{s['node']}"
    else:
        a,b=s["node"]; folder=f"floor{floor}/walks/{s['no']}_{a}__{b}"
    for ph,r in s["members"].items():
        d=os.path.join(OUT,folder,ph); os.makedirs(d,exist_ok=True)
        for sens,data in r["sensors"].items():
            with open(os.path.join(d,sens),"wb") as f: f.write(data)
        manifest.append(dict(
            floor=floor,type=s["kind"],
            node=s["node"] if s["kind"]=="stop" else "",
            from_node=s["node"][0] if s["kind"]=="walk" else "",
            to_node=s["node"][1] if s["kind"]=="walk" else "",
            place=s["place"] or "",
            phone=ph,device={"a55":"SM-A556E","a56":"SM-A566B","iphone":"iPhone19,2"}[ph],
            start_hk=datetime.fromtimestamp(r["start"],HK).strftime("%H:%M:%S"),
            duration_s=round(r["dur"],1),
            n_accel=row_count(r["sensors"].get("Accelerometer.csv",b"")),
            n_gyro=row_count(r["sensors"].get("Gyroscope.csv",b"")),
            n_mag=row_count(r["sensors"].get("Magnetometer.csv",b"")),
            n_baro=row_count(r["sensors"].get("Barometer.csv",b"")),
            pressure_hpa=baro_mean(r["sensors"]),
            folder=folder, source_zip=r["label"]))

# manifest.csv
cols=["floor","type","node","from_node","to_node","place","phone","device","start_hk","duration_s","n_accel","n_gyro","n_mag","n_baro","pressure_hpa","folder","source_zip"]
with open(os.path.join(OUT,"manifest.csv"),"w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
    for m in manifest: w.writerow(m)

# locations.csv
with open(os.path.join(OUT,"locations.csv"),"w",newline="") as f:
    w=csv.writer(f); w.writerow(["floor","stop_no","node","label","n_phones","start_hk","x_m","y_m"])
    for s in slots:
        if s["kind"]!="stop": continue
        w.writerow([s["floor"],s["no"],s["node"],s["place"],len(s["members"]),
                    datetime.fromtimestamp(s["anchor"],HK).strftime("%H:%M:%S"),"",""])
# edges.csv
with open(os.path.join(OUT,"edges.csv"),"w",newline="") as f:
    w=csv.writer(f); w.writerow(["floor","walk_no","from_node","to_node","n_phones","start_hk"])
    for s in slots:
        if s["kind"]!="walk": continue
        w.writerow([s["floor"],s["no"],s["node"][0],s["node"][1],len(s["members"]),
                    datetime.fromtimestamp(s["anchor"],HK).strftime("%H:%M:%S")])

json.dump([{k:(list(v.keys()) if k=="members" else v) for k,v in s.items()} for s in slots],
          open(os.path.join(OUT,"_slots.json"),"w"),indent=1,default=str)
print("tree written:",OUT)
print("stops:",sum(1 for s in slots if s['kind']=='stop'),"walks:",sum(1 for s in slots if s['kind']=='walk'))
print("manifest rows:",len(manifest))
# coverage warnings
for s in slots:
    if len(s["members"])<3:
        miss=[p for p in ("a55","a56","iphone") if p not in s["members"]]
        print("  partial:",s["floor"],s["no"],s["node"],"missing",miss)
