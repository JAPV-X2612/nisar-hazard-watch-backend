# nisar-bench

Benchmark harness that decides **how NISAR data is fetched** for NISAR Hazard Watch: how many threads, which block size, which multilook, which runtime and how fast the fetch and prepare stages are against the 60 s budget of the MVP (Goal 1 of the epic).

It is a self-contained `uv` project (it does not touch the backend's dependencies). It drives DSSA's reference reader (`NISAC_Data_Lab/util/nisac_ts.py`) on **real ASF data**, plans the scenes like the backend will (one track/direction/frame group, up to 5 dates about 30 days apart ending on the newest acquisition, no maturity or configuration filter), and records one row per case.

## Setup

```bash
cd bench
uv sync
```

- `NISAC_LAB_PATH` points to the `NISAC_Data_Lab` folder (default: `/Users/japv-x2612/Documents/NISAC/Backend/NISAC_Data_Lab`); `NISAC_LAB_FILE` can point straight to `nisac_ts.py`.
- **Local runs** read the Earthdata token from the macOS Keychain item `nisac-earthdata-token`. The token is never printed, written or logged (errors are scrubbed).
- **Modal runs** need the Modal CLI logged in (`modal profile current`) and the secret `nisar-hazard-watch-earthdata` with the key `EARTHDATA_TOKEN`. They use the ephemeral app `nisar-hazard-watch-bench` (nothing stays deployed) and cost cents per run: check `modal billing summary` first.

## Commands

```bash
uv run python -m nisar_bench run --runtime local --sites qadirabad --threads 3,5 --run-id local-20261112
uv run python -m nisar_bench run --runtime modal --sites qadirabad,chokwe,richmond --threads 5
uv run python -m nisar_bench run --runtime modal --region us-west --sites qadirabad
uv run python -m nisar_bench report --input results/*.csv --out REPORT.md
uv run python -m nisar_bench defaults --input results/*.csv --out defaults.json
uv run python -m nisar_bench metrics            # offline: lab metrics vs vectorized
uv run python -m nisar_bench compare --baseline baseline.json --input results/new.csv
```

`run` options: `--sites` (`qadirabad`, `chokwe`, `richmond`), `--threads` (scenes read at once), `--readers` (`pyfive`, `h5py`), `--block-mb`, `--multilook`; the matrix is their product and runs one case after another so runs never compete.

## What a row means (`results/*.csv`)

| Column | Meaning |
|---|---|
| `run_id`, `runtime` | group of runs and where they ran (`local`, `modal`, `modal-us-west`) |
| `site`, `threads`, `block_mb`, `multilook`, `n_images`, `use_mask`, `reader` | the case |
| `group`, `dates`, `scenes`, `shape` | the planned group (`track/direction/frame`), the dates read, how many were usable and the output grid |
| `catalog_s` | ASF search plus scene planning |
| `probe_s` | authenticated 1 KB range read (token, EULA and data host check) |
| `read_s` | reading the AOI window of every scene (`construir_pila`), the dominant stage |
| `prepare_s` / `prepare_original_s` | log-ratio plus the seven per-pixel metrics, vectorized against the lab's `metricas_serie` |
| `total_s` | `catalog_s + probe_s + read_s + prepare_s` (empty when the case failed) |
| `requests`, `mb_downloaded`, `valid_pct` | HTTP requests, MB transferred and share of valid pixels |
| `python`, `host`, `cpu_count`, `error` | environment and the scrubbed failure, if any |

`DECISIONS.md` records what was chosen from the first full matrix and why. The fetch-and-prepare budget of the MVP is 22 s (request 1 + auth 1 + fetch 15 + prepare 5). `REPORT.md` compares every runtime with it, names the dominant stage and lists failures; `defaults.json` stores the chosen configuration together with the id of the run that justifies it. `compare` exits 1 and names the stage when a median is more than 20 % slower than a stored baseline (wire it to a manual CI job once the token is a repository secret).

## Limits

- The `defaults` command only compares configurations that ran on the same sites (`--sites`) at least `--min-runs` times; single runs are never recommended.
- Needs DSSA's reader and a valid Earthdata token; every case downloads tens of MB from NASA.
- Only 10.24 km squares (about 105 km²) are measured; larger areas are not calibrated yet.
- L-band only. S-band (ISRO Bhoonidhi) cannot be read on demand and is planned as a precomputed layer.
- Network latency varies a lot between runs (local results differ by tens of seconds): trust medians over several runs, not a single one.
- No AWS is used anywhere; the reads are HTTPS range requests.
