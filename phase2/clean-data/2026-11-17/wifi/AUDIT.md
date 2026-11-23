# Wi-Fi export audit — 2026-11-17

Source log: `WigleWifi_20261117214707.csv.gz`
Export header: `WigleWifi-1.6,appRelease=2.111,model=SM-A556E,release=15,device=a55x,display=AP3A.240905.015.A2.A556EXXSABYI4,board=s5e8845,brand=samsung,star=Sol,body=3,subBody=0`

- 3085 accepted WIFI observations, 2 non-WIFI rows (LTE) separated into `non_wifi_rows.csv`, 0 excluded.
- `FirstSeen` is interpreted as **UTC**, verified by the official WiGLE CSV v1.6 format. Converting to Hong Kong time adds eight hours; this is a display conversion, not a phone-clock adjustment.
- `FirstSeen` records a persisted observation location time, not the radio acquisition time. The exact installed WiGLE 2.111 source/binary was not matched to inspected upstream source.
- Observations are selectively persisted (improved-signal updates), so they are **not** complete fresh scans. Do not fill unobserved access points with -100 dBm or any assumed absence value.
- GPS latitude/longitude/accuracy are original WiGLE metadata only, **not** indoor ground truth or map coordinates.
- Stop association uses exact containment of the stored FirstSeen second inside a recorded stop interval. No nearest-time assignment or interpolation is used.
