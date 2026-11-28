# 27 November 2026 evening: iPhone19,2 (iPhone 18 Pro), 11 stops

*Internal team notes, not report text.*

- **What:** 11 phyphox stops of 60 s each, 17:13 to 17:42 HK, one phone (deviceModel iPhone19,2, the same model as Dicta's
  `sesi1`, `25nov` and `25night`). No walks, no Wi-Fi log. Downloaded by the user on 28 Nov at 04:20; who recorded them was not stated.
- **Files:** `raw/` = the ZIPs byte-identical (`raw_sha256.txt`); `labels_27nov.csv` = one row per ZIP; `clean/` = built by
  `python -I phase2/clean-data/2026-11-27/scripts/build_27nov.py` (sensor folders gitignored, `manifest.csv` and `summary.json` kept).
- **Labels** come from the file names; the build checks each name's floor against pressure (5F stops 1014.28 to 1014.31 hPa,
  4F 1014.94 to 1015.12 hPa) and stops on a mismatch. Medium confidence, as the name had to be interpreted:
  `Esca up` / `Esca down` = the 5F escalator spots; `Disable tolet` (5F) = male disabled toilet (the only disabled toilet
  on 5F); `Disabil tolet umum` (4F, "public") = disabled toilet. `Tolet cewe` = female toilet. `Y5302` = the y5302 spot, not point 2.
- **Session name in the app:** `27nov` (`phase2/new/upload/walksense.py` `ALL_SESSIONS`). PROCESS-LOG entry 95.
