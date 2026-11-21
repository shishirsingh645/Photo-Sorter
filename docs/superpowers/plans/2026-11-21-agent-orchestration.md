# Agent Orchestration Plan — 28 tasks across 3 plans

How the Photo Sorter build is distributed across subagents under
`superpowers:subagent-driven-development`: who runs what, on which model, in
what order, and what must be true before two agents may run at the same time.

**Controller:** this session. It never implements. It dispatches, reviews,
merges, rules, and keeps the ledger.

---

## 0. Prerequisite — subagent dispatch must work

Proven by experiment this session:

| Auto mode | Dispatch |
|---|---|
| OFF | works (probe returned READY) |
| ON | refused, twice |

Cause: context-mode's `PreToolUse` hook, `"matcher": "Agent"`, appends a
`<context_window_protection>` block to every dispatch *after* auto mode has
reviewed it, so auto mode will not vouch for the call it did not see.

Clear one of these before Wave A:

- keep auto mode off, or
- set `"context-mode@context-mode": false` in `~/.claude/settings.json` and
  restart — works even in auto mode, and also recovers `ctx_batch_execute`.

Nothing below runs until this is cleared.

---

## 1. The parallelism problem

SDD's rule is: *never dispatch multiple implementation subagents in
parallel (conflicts).* That rule assumes a single working tree. Two agents
running `git add -A` seconds apart will stage and commit each other's
half-finished files. The failure is silent and the history is unusable.

So parallelism is bought, not free. The price is one git worktree per
concurrent agent, plus a controller merge at the end of each wave.

**DEVIATION FROM SDD, RULED.** Implementers may run concurrently only when
every one of these holds:

1. Each runs in its own worktree created via `superpowers:using-git-worktrees`.
2. Their file sets are provably disjoint — checked against the table in §3
   before dispatch, never assumed.
3. None consumes an interface another is still producing.
4. The controller merges the wave itself, one branch at a time, running the
   full suite after each merge.

Cost if wrong: a bad merge wastes one wave, recoverable from the ledger's
commit list. Benefit: 27 sequential steps collapse to 14 waves.

**Never parallel, regardless:** the reviewer of a diff and the implementer
of the next task touching those files. Review gates the merge.

---

## 2. What actually overlaps

Reviews are the cheap concurrency and carry no merge cost — reviewers only
read. While wave N's reviewers run, wave N+1's implementers can already be
working; the controller holds the merge until the review clears.

```
wave N:    [impl A] [impl B] [impl C]     <- parallel, separate worktrees
              |        |        |
            merge    merge    merge        <- controller, serial, suite after each
              |        |        |
            [rev A]  [rev B]  [rev C]      <- parallel, read-only
                       |
wave N+1:         [impl D] [impl E]        <- may start during review
```

---

## 3. Plan 1 — Core Engine (13 tasks; Task 1 complete)

### Dependency graph

```
T1 config  DONE
 |
 +-- T2 models ---+-- T5 categories+peek --+-- T6 scan
 |                |                        +-- T9 claude labeller -- T10 jev
 +-- T3 platform -+                        +-- T11 apply
 +-- T4 picker                             +-- T12 demo
 |
 +-- T7 dupes
 +-- T8 sheets ----------------------------- T9
                                               |
                                          T13 CLI  <- needs everything
```

### Disjointness table — the pre-dispatch check

| Wave | Task | Creates | Shared-file risk |
|---|---|---|---|
| A | T2 Models | `photosorter/models.py` + test | none |
| A | T3 Platform | `photosorter/platform.py` + test | none |
| A | T4 Picker | `photosorter/picker.py` + test | none |
| B1 | T5 Categories+peek | `core/categories.py`, `core/peek.py`, `categories.json`, 2 tests | creates `core/__init__.py` — see O1 |
| B2 | T7 Dupes | `core/dupes.py` + test | needs `core/__init__.py` |
| B2 | T8 Sheets | `core/sheets.py` + test | needs `core/__init__.py` |
| C | T6 Scan | `core/scan.py` + test | none |
| C | T9 Claude labeller | `core/labelers/{__init__,base,claude}.py` + test | none |
| C | T11 Apply | `core/apply.py` + test | none |
| C | T12 Demo | `core/demo.py` + test | none |
| D | T10 Jev labeller | `core/labelers/jev.py` + test | none |
| E | T13 CLI | `photosorter/__main__.py` + 2 tests | none |

**Ruling O1.** `photosorter/core/__init__.py` is the one file two wave-B
tasks would both create. T5 owns it. T7 and T8 branch from the commit that
merges T5, not from the wave-A head. This is why wave B is split in two.

**Ruling O2.** Per pre-flight R3, T5 defines `PREVIEW_BYTES_PER_FILE = 18_000`
in `core/peek.py` and T6 imports it. T6 sits in wave C, after T5 merges, so
the interface exists before its consumer is dispatched.

### Wave schedule

| Wave | Tasks | Agents | Why grouped |
|---|---|---|---|
| **A** | T2, T3, T4 | 3 | no dependencies, fully disjoint |
| **B1** | T5 | 1 | owns `core/__init__.py`, gates the rest of `core/` |
| **B2** | T7, T8 | 2 | need `core/` to exist, nothing more |
| **C** | T6, T9, T11, T12 | 4 | all consume T5; none consumes another |
| **D** | T10 | 1 | needs T9's `Labeler` protocol |
| **E** | T13 | 1 | wires everything; its smoke test is the integration gate |

12 remaining tasks → **6 waves**.

---

## 4. Plan 2 — API Server (6 tasks)

| Wave | Tasks | Agents | Notes |
|---|---|---|---|
| **A** | T1 app skeleton, state, origin guard | 1 | every other router mounts on it |
| **B** | T2 jobs+SSE, T4 folder routes, T5 file routes, T6 serve+static | 4 | disjoint router files — see O3 |
| **C** | T3 sort/run routes | 1 | needs the job runner from T2 |

**Ruling O3.** `api/schemas.py` is the one genuine shared-file risk here —
T1 creates it and T4 would add `file_manager`. T1 therefore defines the
complete `AppState` up front, including `file_manager` and
`picker_available`, so wave B adds routes only and never edits schemas.
Cost if wrong: one merge conflict in a 40-line file.

---

## 5. Plan 3 — Dashboard (9 tasks)

| Wave | Tasks | Agents | Notes |
|---|---|---|---|
| **A** | T1 scaffold, tokens, theme | 1 | everything imports the tokens |
| **B** | T2 api client+hooks, T3 chrome components, T5 animation | 3 | disjoint dirs: `api/`+`state/`, `components/`, `anim/` |
| **C** | T4 setup card, T6 run+done panels, T7 dialogs | 3 | all consume T2/T3; disjoint component files |
| **D** | T8 demo, URL params, build | 1 | modifies `App.tsx`, commits `web/dist/` |
| **E** | T9 Windows verification | 1 | manual, needs the built app |

9 tasks → **5 waves**.

---

## 6. Model assignment

Cheapest model that can do the job; turn count beats token price; always
specify the model explicitly, since omitting it silently inherits the
session's most expensive one.

| Tier | Tasks | Why |
|---|---|---|
| **Cheap** (haiku) | P1-T2 models, T4 picker, T8 sheets, T12 demo; P3-T1 scaffold | the plan text carries the tests; the work is transcription plus running them |
| **Standard** (sonnet) | P1-T3 platform, T5, T6 scan, T9 claude, T10 jev, T11 apply; P2-T1, T4, T5, T6; P3-T2, T3, T4, T6, T7 | multi-file, real integration, judgment on error paths |
| **Most capable** (opus) | P1-T7 dupes, P1-T13 CLI, P2-T2 jobs+SSE, P2-T3 sort routes, P3-T5 animation, P3-T8 build, all three final reviews | algorithmic correctness, concurrency, cross-cutting integration, frame budget |

Four tasks earn the top tier on their own merits:

- **P1-T7 dupes** — the pigeonhole-banding proof is the one place a subtle
  error silently misfiles photos while every test still passes. It also
  owns the exactness-versus-bruteforce test.
- **P2-T2 jobs+SSE** — threads, an asyncio queue, subscriber lifecycle and a
  cancellation path. Classic concurrency-bug territory.
- **P3-T5 animation** — must hold 60fps with 320 tiles and stay outside
  React state. A cheap model reaches for `useState` and quietly loses the
  feel the replica exists to reproduce.
- **P1-T13 CLI** — the first point where all 12 prior tasks meet.

### Reviewers

Scale to the diff, not the task.

| Diff shape | Reviewer |
|---|---|
| single file, mechanical (T2, T4, T8, T12) | cheap |
| multi-file or user-facing behaviour (most) | standard |
| T7, T13, P2-T2, P3-T5, and every fix round 4–5 | most capable |
| the three whole-branch final reviews | most capable, always |

Fix-loop escalation uses a model at least one tier above the implementer
that got stuck.

---

## 7. Controller protocol, per wave

1. Record `BASE = git rev-parse HEAD`.
2. Check the wave's tasks against the §3 disjointness table. A pair not
   listed there as disjoint is not dispatched together.
3. Create one worktree per task in the wave.
4. Generate each brief (`scripts/task-brief PLAN_FILE N`). Each dispatch
   carries: one line of placement, the brief path, the interfaces earlier
   tasks produced, the resolved ambiguities, the report path. **Never the
   whole plan file. Never prior-task history.**
4a. **Point every dispatch at the knowledge graph.** Each prompt gets a short
   "Orient yourself first" block naming `graphify-out/` and the three
   commands — `graphify query "<question>"`, `graphify path "A" "B"`,
   `graphify explain "<node>"` — plus `graphify-out/GRAPH_REPORT.md` for the
   god nodes and community map. A fresh agent should read the graph before
   reading source: crawling the repo spends its context on structure one
   query already answers. The task brief remains the authority on
   requirements; the graph is for navigation only. Refresh the graph after a
   batch of merges, since it reflects `main` at build time.
5. Carry the standing rulings into every dispatch: no `Co-Authored-By`
   trailer; `def test_x(): ...` means write the real assertions (pre-flight
   R5); no `sys.platform` outside `platform.py`; explicit utf-8; `pathlib`
   only; nothing O(n²).
6. Collect reports. Merge branches one at a time, running the full suite
   after each. A merge that reddens the suite is reverted, not patched
   forward.
7. Generate a review package per task
   (`scripts/review-package PLAN_FILE BASE HEAD`) and dispatch reviewers in
   parallel.
8. Fix loop per `references/fix-loop.md`, re-read before every round.
9. Append one completion line per task to the ledger, then start the next
   wave.

---

## 8. Cost and schedule

| | Sequential SDD | Waved |
|---|---|---|
| Plan 1 (12 remaining) | 12 steps | 6 waves |
| Plan 2 (6) | 6 steps | 3 waves |
| Plan 3 (9) | 9 steps | 5 waves |
| **Total** | **27 steps** | **14 waves** |

Agent seats: 27 implementers + 27 reviewers + 3 final reviewers = **57**,
unchanged by waving. Parallelism buys wall-clock, not seats. Added cost:
roughly 20 worktree create-and-merge cycles of controller time.

Peak concurrency is 4, in Plan 1 wave C. Do not exceed 4 — beyond that the
controller's serial merge-and-suite step becomes the bottleneck and the wave
stops paying for itself.

---

## 9. Deliberately not parallelised

- **P1-T13, P2-T3, P3-T8** — the integration tasks. Each one's value is
  seeing every prior piece fit together; splitting them defeats the point.
- **P3-T9** — manual Windows verification, watched by a human.
- **The three final whole-branch reviews** — one reviewer must hold the
  whole branch in view. Splitting that is how cross-cutting defects survive.
- **Anything inside a fix loop.** A task under review belongs to one
  implementer until its findings are closed or parked at the cap.

---

## 10. Failure modes this plan guards against

| Risk | Guard |
|---|---|
| Two agents staging each other's files | one worktree per concurrent agent (§1) |
| Two agents both creating `core/__init__.py` | Ruling O1 — T5 owns it, wave B splits in two |
| A consumer dispatched before its producer merges | waves follow the dependency graph, not convenience |
| Reviewers rejecting the plan's own `...` test shorthand | pre-flight R5 carried into every dispatch and review prompt |
| Controller losing its place after compaction | ledger with per-task commit SHAs; trust it and `git log` over memory |
| A cheap model quietly under-building T7 or P3-T5 | explicit top-tier assignment (§6) |
| A merge reddening the suite | revert the merge and re-dispatch; the controller never patches forward |
