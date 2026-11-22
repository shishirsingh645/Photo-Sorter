# Build / Test ledger

Testing is deliberately deferred: nothing below has had its tests run since
2026-11-22. Run the full suite only when Plan 3 is complete.

Last green suite: 206 tests, at 6101836 (end of Plan 1).

## Built AND tested (suite green at the time)

| Area | Where | Evidence |
|---|---|---|
| Plan 1 — whole core engine (13 tasks) | `photosorter/core/`, `config.py`, `models.py`, `platform.py`, `picker.py`, `__main__.py` | 206 tests green at 6101836 |
| P2 T1 — app factory, origin+Host guard, `/api/state` | `api/app.py`, `api/schemas.py`, `api/routes_state.py` | tests ran in-task, merged dee2a34 |
| P2 T5 — file routes, range requests, conversion | `api/routes_files.py` | tests ran in-task, merged 665790f |
| P2 T6 — serve command, frontend mount | `api/serve.py`, `api/static.py` | tests ran in-task, merged 4c4c2b9 |

## Built, tests WRITTEN but NOT RUN on main

| Area | Where | Tests to run |
|---|---|---|
| P2 T2 — job runner, SSE stream | `photosorter/jobs.py`, `api/routes_events.py` | `tests/test_jobs.py`, `tests/api/test_events.py` |
| P2 T4 — peek/pick/open/categories/move routes | `api/routes_folders.py`, `core/categories.py`, `core/apply.py` | `tests/api/test_folders_routes.py`, `tests/test_apply.py` |

## Still to build

| Item | Plan |
|---|---|
| P2 T3 — `/api/sort`, `/api/run`, `/api/cancel`, `/api/labels` | Plan 2 |
| Plan 3 — the dashboard, 9 tasks | Plan 3 |
| Jev (TypeSafe) labeller — spec 7.2, backlog item B1 | unplanned |

## To test at the end

1. `pytest` — the whole suite, after Plan 3.
2. The merged-but-unrun P2 T2 / T4 suites above are the first suspects on failure.
3. End-to-end: `photosorter serve`, a real sort over HTTP, a browser reload mid-sort.
