# Benchmark report

18 runs (18 clean, 0 failed) across 3 runtime(s); run ids: local-20261112, modal-20261112, modal-us-west-20261112.

## Median by configuration (seconds, MB)

| runtime | threads | block_mb | multilook | n_images | reader | catalog_s | probe_s | read_s | prepare_s | total_s | requests | mb_downloaded | runs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| local | 3 | 1.0 | 2 | 5 | pyfive | 4.65 | 4.09 | 83.85 | 0.03 | 92.62 | 156.0 | 77.5 | 1 |
| local | 5 | 1.0 | 2 | 5 | pyfive | 2.0 | 3.85 | 42.15 | 0.02 | 48.02 | 117.5 | 60.75 | 2 |
| modal | 3 | 1.0 | 2 | 5 | pyfive | 0.72 | 1.78 | 12.82 | 0.08 | 15.4 | 156.0 | 77.5 | 1 |
| modal | 5 | 1.0 | 1 | 5 | pyfive | 0.76 | 2.04 | 16.77 | 0.26 | 19.83 | 156.0 | 77.5 | 1 |
| modal | 5 | 1.0 | 2 | 5 | h5py | 0.68 | 2.51 | 200.3 | 0.08 | 203.57 | 111.0 | 111.0 | 1 |
| modal | 5 | 1.0 | 2 | 5 | pyfive | 0.78 | 2.45 | 10.8 | 0.09 | 14.09 | 156.0 | 77.5 | 5 |
| modal | 5 | 4.0 | 2 | 5 | pyfive | 0.59 | 2.0 | 10.27 | 0.08 | 12.94 | 151.0 | 120.5 | 1 |
| modal | 8 | 1.0 | 2 | 5 | pyfive | 0.79 | 1.31 | 6.94 | 0.07 | 9.11 | 156.0 | 77.5 | 1 |
| modal-us-west | 5 | 1.0 | 2 | 5 | pyfive | 0.93 | 1.54 | 7.96 | 0.08 | 10.84 | 156.0 | 77.5 | 5 |

## Median by site and configuration

| site | runtime | threads | block_mb | multilook | n_images | reader | catalog_s | probe_s | read_s | prepare_s | total_s | requests | mb_downloaded |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| chokwe | modal | 5 | 1.0 | 2 | 5 | pyfive | 1.9 | 3.91 | 21.87 | 0.1 | 27.78 | 156.0 | 77.5 |
| chokwe | modal-us-west | 5 | 1.0 | 2 | 5 | pyfive | 0.7 | 1.38 | 8.77 | 0.08 | 10.93 | 156.0 | 77.5 |
| qadirabad | local | 3 | 1.0 | 2 | 5 | pyfive | 4.65 | 4.09 | 83.85 | 0.03 | 92.62 | 156.0 | 77.5 |
| qadirabad | local | 5 | 1.0 | 2 | 5 | pyfive | 0.95 | 3.52 | 50.37 | 0.03 | 54.87 | 156.0 | 77.5 |
| qadirabad | modal | 3 | 1.0 | 2 | 5 | pyfive | 0.72 | 1.78 | 12.82 | 0.08 | 15.4 | 156.0 | 77.5 |
| qadirabad | modal | 5 | 1.0 | 1 | 5 | pyfive | 0.76 | 2.04 | 16.77 | 0.26 | 19.83 | 156.0 | 77.5 |
| qadirabad | modal | 5 | 1.0 | 2 | 5 | h5py | 0.68 | 2.51 | 200.3 | 0.08 | 203.57 | 111.0 | 111.0 |
| qadirabad | modal | 5 | 1.0 | 2 | 5 | pyfive | 0.75 | 2.09 | 10.72 | 0.09 | 13.68 | 156.0 | 77.5 |
| qadirabad | modal | 5 | 4.0 | 2 | 5 | pyfive | 0.59 | 2.0 | 10.27 | 0.08 | 12.94 | 151.0 | 120.5 |
| qadirabad | modal | 8 | 1.0 | 2 | 5 | pyfive | 0.79 | 1.31 | 6.94 | 0.07 | 9.11 | 156.0 | 77.5 |
| qadirabad | modal-us-west | 5 | 1.0 | 2 | 5 | pyfive | 0.93 | 1.66 | 7.96 | 0.08 | 10.84 | 156.0 | 77.5 |
| richmond | local | 5 | 1.0 | 2 | 5 | pyfive | 3.06 | 4.18 | 33.93 | 0.01 | 41.18 | 79.0 | 44.0 |
| richmond | modal | 5 | 1.0 | 2 | 5 | pyfive | 1.45 | 3.61 | 19.77 | 0.02 | 24.85 | 79.0 | 44.0 |
| richmond | modal-us-west | 5 | 1.0 | 2 | 5 | pyfive | 0.84 | 1.42 | 6.71 | 0.03 | 9.0 | 79.0 | 44.0 |

## Budget (22 s for catalog + auth + fetch + prepare)

- **local**: median total 54.9 s does not fit the 22 s budget; dominant stage `read_s` (50.4 s).
- **modal**: median total 14.7 s fits the 22 s budget; dominant stage `read_s` (11.8 s).
- **modal-us-west**: median total 10.8 s fits the 22 s budget; dominant stage `read_s` (8.0 s).

Fastest runtime: **modal-us-west** (median total 10.8 s).

## Prepare stage

Vectorized metrics take a median 0.08 s against 13.81 s for the original `metricas_serie` (172.6x).
