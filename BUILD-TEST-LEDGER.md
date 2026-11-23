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
| P2 T3 — `/api/sort`, `/api/run`, `/api/cancel`, `/api/labels` | `api/routes_jobs.py` | `tests/api/test_jobs_routes.py` |
| P3 T1 — scaffold, design tokens, theme | `web/` (Vite, React, TypeScript), `styles/tokens.css`, `hooks/useTheme.ts` | `web/src/hooks/useTheme.test.ts` |
| P3 T2 — typed API client, reducer, the two hooks | `api/client.ts`, `state/reducer.ts`, `hooks/useAppState.ts`, `hooks/useJobEvents.ts` | `web/src/api/client.test.ts`, `state/reducer.test.ts`, `hooks/useJobEvents.test.ts` |
| P3 T3 — chrome: top bar, KPI row, folder cards, board | `components/Topbar.tsx`, `KpiRow.tsx`, `FolderCard.tsx`, `Board.tsx`, `TitleRow.tsx` | `web/src/components/{Topbar,KpiRow,FolderCard,Board,TitleRow}.test.tsx`, `web/src/format.test.ts` |
| P3 T4 — setup card, Advanced panel, estimates | `components/SetupCard.tsx`, `AdvancedPanel.tsx`, `estimates.ts` | `web/src/components/SetupCard.test.tsx`, `estimates.test.ts` |
| P3 T5 — animation layer: sphere, fly, loop, confetti, player | `anim/`, `components/Stage.tsx`, `state/board.ts` | `web/src/anim/{sphere,fly,player}.test.ts`, `components/Stage.test.tsx`, `state/board.test.ts` |
| P3 T6 — running panel and done panel | `components/RunCard.tsx`, `DonePanel.tsx`, `progress.ts` | `web/src/components/{RunCard,DonePanel}.test.tsx`, `progress.test.ts` |
| P3 T7 — dialogs: folders, browse, lightbox, paid confirm | `components/Dialog.tsx`, `FoldersDialog.tsx`, `BrowseDialog.tsx`, `Lightbox.tsx`, `PaidConfirm.tsx` | `web/src/components/{Dialog,FoldersDialog,BrowseDialog,Lightbox,PaidConfirm}.test.tsx` |
| P3 T8 — assembly, demo mode, URL parameters, built `web/dist` (the 20-row parity sweep is deferred by ruling P3-4) | `App.tsx`, `demo.ts`, `state/library.ts`, `styles/components.css`, `web/dist/` | `web/src/App.test.tsx` (including the live-sort tests), `demo.test.ts`, `state/library.test.ts`, `styles/components.test.ts` |
| P3 T8 final-review fixes (state refresh, inventory cache, sphere anchor, demo lightbox, dev proxy, reduced motion) | `App.tsx`, `anim/sphere.ts`, `components/{Stage,Lightbox,BrowseDialog}.tsx`, `vite.config.ts`, `photosorter/api/app.py` | the files above, plus `tests/api/test_origin_guard.py` (security-sensitive: the Origin guard's dev-only allowance) |
| P3 T9 — platform support document (no automated test: its check is a manual pass, recorded in the document) | `docs/platform-support.md` | none to run |

## Still to build

| Item | Plan |
|---|---|
| Jev (TypeSafe) labeller — spec 7.2, backlog item B1 | unplanned |

## To test at the end

1. `pytest` for the engine and server, and `npm test` in `web/` for the dashboard: the whole suite, after Plan 3. Plan 3 is built; nothing in its nine rows above has been run.
2. The merged-but-unrun P2 T2 / T3 / T4 suites above (including `tests/api/test_jobs_routes.py`), and `tests/api/test_origin_guard.py` (the Origin guard's dev-only allowance, the project's one security-sensitive change: run it first), are the first suspects on failure.
3. End-to-end: `photosorter serve`, a real sort over HTTP, a browser reload mid-sort.
