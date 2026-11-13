# CLAUDE.md — nisar-hazard-watch-backend

FastAPI backend of NISAR Hazard Watch (NASA Space Apps 2026, "Dancing with the SARs"). The approved plan and measured evidence live in `DELETE/planning/nisac-mvp-realtime-hazard-pipeline.md` (git-ignored); team context in `~/.claude/memory/NISAC_2026.md`.

## Commands
- `uv sync` · `uv run pytest` (unit, 80 % gate) · `uv run pytest -m integration` (needs `DATABASE_URL`) · `uv run pytest -m live` (real NASA)
- `uv run ruff check && uv run ruff format --check && uv run pyright` before every commit
- `uv run alembic upgrade head` · `docker compose up --build`

## Architecture (hexagonal)
`api → services → ports ← adapters`, plus `models/` (DTOs), `constants/`, `config/`, `exceptions/`, `utils/`. Wire concrete adapters only in `api/composition.py`. New routers are registered in `api/routes/router.py`. Python 3.13, async everywhere, SQLAlchemy 2 + Alembic.

## Conventions
- English everywhere (code, comments, commits, PRs); chat with the team lead in Spanish.
- No magic strings: routes, reason codes and enums live in `constants/` (`StrEnum`).
- DTOs subclass `CamelModel`; payloads are camelCase; errors are `application/problem+json` with `reasonCode` and `requestId`.
- One concept per file, one kind of thing per folder; helpers in `utils/`, interfaces in `ports/`.
- Tests mirror the source path (`test_<file>.py`), carry `# Arrange`, `# Act`, `# Assert`, keep constants at module top, use no network (`live` marker for real calls, `integration` for Postgres) and avoid long end-to-end suites per small change.
- Comments only for non-obvious *why*; docstrings never longer than the code.

## Science honesty
Results are diagnostic evidence, not validated classifiers. Every result carries `isDemo: false`, `limitations[]` and `scientificStatus`; never invent numbers; displacement and hectares stay null until validated. L-band (ASF) is the only on-demand source in the MVP; S-band (ISRO Bhoonidhi) arrives later as a precomputed layer and needs the credit "ISRO-IRS".

## Git
- `main` is production. Branch from `origin/main` (`git switch -c <type>/<name> --no-track origin/main`), open a PR, never push to `main`, never force-push, never merge your own PR.
- Conventional commits (`feat:`, `fix:`, `chore:`, `ci:`, `build:`, `docs:`, `test:`, `refactor:`) ending with the `Co-Authored-By` trailer; PR descriptions end with the Claude Code footer.
- Use `gh` and `git` as `JAPV-X2612` only. The active `gh` account and the global git identity can be a company account: check `gh api user --jq .login` before pushing; never run `gh auth switch`.

## Secrets and platforms
- Tokens and keys live in the macOS Keychain (`nisac-earthdata-token`, `nisac-bhoonidhi-*`, `nisac-firms-map-key`) and as platform secrets (Railway, Vercel, Modal, GitHub); never in code, logs, files, memory or commits. When the team lead pastes one in chat or asks for it, Claude may use the value to set it as a platform secret and in the Keychain, and may read Keychain items and platform variables (`list-variables`) to configure or validate, without repeating the value in replies. Copy it exactly (one retyped character once caused a false 401) and prove it with a real call after setting it.
- Names share the base `nisar-hazard-watch`: Railway project, services `nisar-hazard-watch-backend` and `nisar-hazard-watch-db`, bucket `nisar-hazard-watch-artifacts`; Vercel project `nisar-hazard-watch`; Modal apps `nisar-hazard-watch-ml` and `-ml-dev`.
- Never touch or deploy anything on AWS (any account or region). Tell the team lead at once if Vercel, Modal or Railway credits run out.
- Never create files under `docs/`; plans and notes go under `.superpowers/` or `DELETE/` (git-ignored).
