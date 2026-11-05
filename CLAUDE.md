# Roastery - guidance for Claude Code

A Bergen coffee roaster as software: the shop app, the simulator that plays its trade
through the app, and the data contract its extracts are held to. README.md has the install
and the commands; `docs/phase-6/plan.md` is the plan.

## Start here

1. Read **Status** at the top of `docs/phase-6/plan.md`; the first unticked step is current.
2. Read that step's plan file (none yet for 6.5; 6.4's is `docs/phase-6/6.4-week.md`) and work from its first
   unticked unit.
3. The record lives in files, not in a session:
   - a step's box is ticked, with its commit hash, in the commit that finishes the step;
   - what turned out different goes in the Notes, dated, with the step or unit;
   - a decision is a new numbered row (D16, S9, ...), never a decision reopened silently.
4. When the context runs low, first write where you stand into the step's plan.

## The repo

| package | import | what |
|---|---|---|
| `packages/shop` | `roastery` | the app: domain, service layer, stores |
| `packages/sim` | `roastery_sim` | the simulator, the outside systems, the export writer |
| `packages/spec` | `roastery_spec` | the data contract and its claims, as tests |

The data-docs repository beside this one is a learning site. It reads a pinned
`roastery-data` release and is never imported from here; steps 6.1 to 6.5 never touch it.

## Rules

- Shown code in `packages/shop` has 72-character lines (its `ruff.toml`); 100 elsewhere.
- No module state; no wall clock: time comes through the `Clock` port.
- Money is `Decimal`; outputs and listings are sorted; e-mails end in `example.invalid`.
- Determinism: the same seed gives the same bytes.
- Ruff: single quotes, docstrings in double quotes (the Q rule).
- Python 3.13 via uv. Run the suite as `uv run python -m pytest`, never `uv run pytest`.
- No `pytest.skip` to hide unbuilt work: claims whose tables are missing are deselected and
  listed under "awaiting data" (6.1 §2, S6).
- A failing test is fixed at its subject, never by weakening the assertion.
- Nothing committed holds a machine path or a secret. Never open an `ANSWER_KEY.md`.

## Freezes

| what | frozen | a change means |
|---|---|---|
| `tiny`: its tables, rows and columns | now (it is data-docs' dataset) | not allowed; new columns live in `month` and `full` (D13) |
| contract B, the simulator's call surface | after 6.4 (tag `shop 0.1.0`) | a new data version |
| anything in a release, after `roastery-data 1.0` | at the release | a new data version with an entry in `docs/data-changelog.md` |

## Working with agents

Large work runs through subagents, so the lead session keeps its context.

- **The lead plans, briefs, checks and commits; agents do the units.** One agent per
  self-contained unit (a table's claims, a test file, `contract.md`). The lead does not read
  large files (data files, the baseline `.sql`, whole test files): an agent reads them and
  returns the conclusion.
- **A brief has five parts:** the goal; the files to read, by path, not retyped; the "done
  when"; what not to touch; the reply (a short summary, the files changed, the test result,
  no file dumps).
- **The model follows the cost of a quiet mistake, not the size of the task.** When unsure,
  take the stronger one; work that fails or looks doubtful is run again one model up.

  | model | for |
  |---|---|
  | `opus` | judgment: `contract.md`, claims that carry a lesson, `order`, `pricing`, `vat`, architecture, reviews, a failure that repeats, planning |
  | `sonnet` | building to a clear spec: porting a test file, a module against its ADR, a store twin |
  | `haiku` | lookups and sweeps: every file that reads X, test names checked, table inventories |

- **Agents never commit** and never push. The lead runs the step's tests itself before it
  calls an agent's unit done. One heavy job at a time.
- **Reviews:** the advisor before a step is called done; `/code-review` before a release
  (6.5) and before 6.6's merge; `security-review` on `packages/shop` before 6.5.

## Commits and releases

- Commit only your own paths: `git add <path>`, never `-A`.
- Push, tag and release only on the owner's word.
- Commit messages end with the Co-Authored-By line the session is given.

## Commands

| command | what |
|---|---|
| `uv sync` | install the workspace (CI runs `uv sync --locked`) |
| `uv run python -m pytest` | the suite |
| `uv run ruff check` | lint |
| `uv run ruff format --check` | formatting, as CI checks it |

## Machine (Windows 11)

- PowerShell is primary; Git Bash for scripts.
- `cp` and `rm` can prompt and hang: use git or Python.
- Heredocs eat backslashes.
- Write text with `newline` set to LF; a `>` redirect in PowerShell writes UTF-16.
