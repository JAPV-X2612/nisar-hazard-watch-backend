# Calibration decisions (Goal 1)

Measured on 2026-11-12 with real ASF data and a real Earthdata token (18 runs, none failed; ids `local-20261112`, `modal-20261112`, `modal-us-west-20261112`). Numbers are medians of `total_s` = catalog + auth probe + fetch + prepare, against the 22 s budget of the MVP (request 1 + auth 1 + fetch 15 + prepare 5). Raw rows: `results/*.csv`; generated tables and the chart: `REPORT.md`, `results/stage-breakdown.png`. The chosen configuration and the run that justifies it are in `defaults.json`.

| Decision | Evidence | Choice |
|---|---|---|
| **Runtime** | Qadirabad: local 54.9 s (1 run) · Modal default region 13.7 s (3 runs) · **Modal `us-west` 10.8 s (3 runs)**. Chókwè: 27.8 s default vs **10.9 s** `us-west`. Richmond: 24.8 s default vs **9.0 s** `us-west`. The same scene window costs 30–50 s from a laptop in Colombia, ~10 s in Modal default and ~7 s in `us-west` (ASF serves from AWS us-west-2). | **Modal, region `us-west`**; only it fits the budget at all three sites. Railway was not measured (the backend only plans). |
| **HDF5 reader** | `pyfive` 13.7 s against `h5py` 203.6 s (1 run, 111 requests): `pyfive` fetches the AOI chunks with parallel exact-range reads, `h5py` over a Python file object reads them serially. | **`pyfive`** |
| **Threads** | 3 → 15.4 s, 5 → 13.7 s (3 runs), 8 → 9.1 s (1 run). Threads only help up to the number of scenes read at once (5), so the 8-thread result is run-to-run variance, not a trend. | **5 = images per request** |
| **Block size** | 4 MB downloads 120 MB instead of 77 MB for no gain (12.9 s, 1 run). | **1 MB** |
| **Multilook** | 1 → 19.8 s and a 1024×1024 grid; 2 → 13.7 s and 512×512. | **2** |
| **Prepare stage** | Vectorized log-ratio and seven metrics 0.08 s against 13.8 s for the lab's `metricas_serie` (172×, same values to 3e-7). | **Vectorized metrics** |
| **Area** | Only the 10.24 km square (≈105 km²) was measured. | Keep the Goal 3 limits (ideal ≈110 km², hard cap 400 km²); larger areas need a new measurement before the cap is trusted. |

## What this leaves for the rest of the pipeline

Fetch plus prepare takes about 11 s at the three measured sites in `us-west`, so 49 s of the 60 s budget remain for analysis, delivery and rendering. Chókwè and Richmond in the default region (24.8–27.8 s) would already exceed the fetch budget, which is why the region is part of the decision.

## Limits of this evidence

- One afternoon from one laptop and one Modal workspace; ASF edge caches may be warm for repeated windows (Qadirabad was run most often).
- Single runs for local, h5py, block size, multilook and 3 or 8 threads: trust them as order-of-magnitude, not as rankings.
- Cold-start time of a Modal container is not part of these numbers (the clock starts inside the function); Goal 4 measures it with memory snapshots.
- L-band GCOV only.
