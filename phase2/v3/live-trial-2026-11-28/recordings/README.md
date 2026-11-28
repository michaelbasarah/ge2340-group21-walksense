# Live-walk trial recordings — 28 Nov 2026

Phyphox recordings auto-saved by `server.py --live` during Dicta's live-walk attempt on her **iPhone 18 (iPhone19,2)**. Each file is one phyphox play→pause (Accelerometer, Gyroscope, Magnetometer, Barometer + `meta/device.csv`), laid out like a phyphox export, so it can be **uploaded through the app** (`Upload a recording`) or added to a dataset.

| File | Saved (HKT) |
|---|---|
| `20261128-173954.zip` | 17:39 |
| `20261128-174641.zip` | 17:46 |
| `20261128-175521.zip` | 17:55 |
| `20261128-180234.zip` | 18:02 |

These are **test trials, not clean training data** — the live feed was repeatedly cut by the laptop's VPN (see `../../HANDOFF.md`), so they are mixed walking/standing with gaps. Use them to replay floor + place detection through `phase2/v3/upload`, not as new fingerprints. Committed (force-added past the `recordings/` gitignore) so the teammate can test without the phone.
