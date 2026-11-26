# WalkSense route — 26 November 2026 morning, Tian (ip16 = iPhone17,4), floor 5 + floor 4

Built by `../scripts/build_tian26.py` from `../labels_tian26.csv` (labels = Tian's chat captions).

## Floor 5

13 stops, 14 walks.

| # | time | type | place | caption |
|---|------|------|-------|---------|
| s01 | 09:30:30 | STOP | Exit 5 door | exit 5 |
| w01 | 09:32:27 | walk | exit5_door → male_toilet | exit 5 toilet men |
| s02 | 09:33:13 | STOP | Male toilet | toilet men |
| w02 | 09:34:48 | walk | male_toilet → y5302 | toilet men y5302 |
| s03 | 09:35:21 | STOP | Y5302 | y5302 |
| w03 | 09:36:42 | walk | y5302 → sr9 | y5302 sr9 |
| s04 | 09:37:19 | STOP | SR9 (study rooms) | sr9 |
| w04 | 09:38:46 | walk | sr9 → y5202 | sr9 y5202 |
| s05 | 09:39:15 | STOP | Y5202 | y5202 |
| w05 | 09:40:41 | walk | y5202 → female_toilet | y5202 toilet cewe |
| s06 | 09:42:27 | STOP | Female toilet | toilet cewe |
| w06 | 09:44:04 | walk | female_toilet → exit10_door | toilet cewe exit 10 |
| s07 | 09:44:44 | STOP | Exit 10 door | exit 10 |
| w07 | 09:46:59 | walk | exit10_door → canteen | exit 10 canteen |
| w08 | 09:48:40 | walk | canteen → esca_down | canteen esc turun atas |
| w09 | 09:49:10 | walk | esca_up → canteen | eska naik atas kantin |
| w10 | 09:49:41 | walk | esca_up → esca_down | eska naik atas eska turun atas |
| s08 | 09:50:06 | STOP | Escalator down | eska turun atas |
| s09 | 09:56:18 | STOP | Escalator up | eska naik atas |
| w11 | 09:58:54 | walk | exit5_door → male_disabled_toilet | esit 5 toilet disabled men |
| s10 | 09:59:25 | STOP | Male disabled toilet | toilet disabled men |
| w12 | 10:00:51 | walk | male_disabled_toilet → lift_stairs5 | toilet disabled men lift stair |
| s11 | 10:01:57 | STOP | Lift / stairs 5 | stair lift |
| w13 | 10:03:48 | walk | lift_stairs5 → y5401 | lift stair y5401 |
| s12 | 10:04:29 | STOP | Y5401 | y5401 |
| w14 | 10:05:45 | walk | y5401 → y5302_point2 | y5401 y5302 back |
| s13 | 10:06:35 | STOP | Y5302 (point 2 - other door) | y5302 back |

## Floor 4

12 stops, 13 walks.

| # | time | type | place | caption |
|---|------|------|-------|---------|
| s01 | 10:09:46 | STOP | Lift / stairs 5 (floor-4 landing) | stair lift bawah |
| w01 | 10:11:07 | walk | lift_stairs5 → disabled_toilet | lift stair bawah toilet disabled bawah |
| s02 | 10:11:37 | STOP | Disabled toilet | toilet disabled bawah |
| w02 | 10:13:07 | walk | disabled_toilet → exit5_door | disabled bawah exit 5 bawah |
| s03 | 10:14:52 | STOP | Exit 5 door | exit 5 bawah |
| w03 | 10:16:18 | walk | exit5_door → lt2a | exit 5 bawah lt 2a |
| s04 | 10:16:55 | STOP | LT2A | lt2a |
| w04 | 10:19:04 | walk | lt2a → lt2b | lt2a 2b |
| s05 | 10:19:38 | STOP | LT2B | lt 2b |
| w05 | 10:21:16 | walk | lt2b → esca_down | lt2b esc turun bawah |
| s06 | 10:22:01 | STOP | Escalator down | lift turun bawah (medium)|
| w06 | 10:24:31 | walk | esca_down → esca_up | esc turun bawah esc naik bawah |
| w07 | 10:25:06 | walk | esca_down → y4502 | esc turun bawah y4502 |
| s07 | 10:25:34 | STOP | Y4502 | y4502 |
| w08 | 10:26:58 | walk | y4502 → esca_up | y4502 esc naik bawah |
| s08 | 10:27:36 | STOP | Escalator up | esc naik bawah |
| w09 | 10:29:11 | walk | esca_up → lt1b | esc naik bawah lt 1 b |
| s09 | 10:29:50 | STOP | LT1B | lt1b |
| w10 | 10:31:28 | walk | lt1b → lt1a | lt1b lt1a |
| s10 | 10:32:18 | STOP | LT1A | lt1a |
| w11 | 10:33:49 | walk | lt1a → exit10_door | lt1b exit 10 (medium)|
| s11 | 10:34:12 | STOP | Exit 10 door | exit 10 bawah |
| w12 | 10:35:33 | walk | exit10_door → gate | exit 10 bawah main gate |
| s12 | 10:36:41 | STOP | Gate (building entrance/exit) | main gate bawah |
| w13 | 10:38:16 | walk | gate → exit5_door | main gate bawah exit 5 bawah |

## Notes

- No canteen stop (the run starts at the exit 5 door) and no 5F exit 5 -> ... walk from the escalators: between the 5F escalator-up stop and "esit 5 toilet disabled men" nothing was recorded.
- Two captions contradict their neighbours and were resolved from the sequence (confidence medium): "lift turun bawah" = escalator down 4F stop, "lt1b exit 10" = walk LT1A -> exit 10 door 4F.
