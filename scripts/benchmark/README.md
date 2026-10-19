# Benchmark question picker

Python 3.9+ standard library; pytest is required for the test suite and Python
replays. Go, bash and (for TypeScript) locally installed Vitest are runtime tools.
Only run verification against trusted repository history: exported tests execute
with your user privileges; this tool is not a security sandbox.

```bash
python3 scripts/benchmark/pick.py > candidates.jsonl
# Optional: explicit local repositories, reference and history window
python3 scripts/benchmark/pick.py /path/to/repo --ref main --days 60

# One candidate, zero-based JSONL index; each test command has its own timeout
python3 scripts/benchmark/verify.py candidates.jsonl --index 0 --timeout 120 > verified.jsonl
# Append additional verification results using other --index values.
python3 scripts/benchmark/select.py verified.jsonl --output questions.json
python3 -m pytest -q scripts/benchmark
```

`pick.py` reads local Git history only (`main`, last 150 days by default); it does
not fetch. An unavailable repository/ref is reported on stderr with nonzero exit
status, while other repositories are still scanned. Root/merge commits, deleted
tests, commits touching `k8s/`, `.env*`, or `*.secret*` (including rename sources)
are excluded. Regression evidence may be explicit regression wording, a review 2NN reference,
a fix tied to an A1–A9/B1–B9 item, or a changed test named for a review. The final
Git trailer block is removed from task text; no patch is included. There is one
candidate per language per commit. Python tests naming a changed `.sh` script
are categorized as shell; shell harnesses use `test_*.sh` or `*_test.sh` names.
Go and Python candidates require recognizable changed test functions; changes
only to helpers are conservatively skipped. No LLM makes selection decisions.

`tests_to_run` is a list of `{cwd, argv}` objects, without shell interpolation.
Go packages are relative to the nearest `go.mod`; TypeScript test paths are
relative to the nearest `package.json`. Python uses changed `test_*` function
names in a pytest `-k` expression (including changed existing tests). No packages
are installed. Verification does not bootstrap project-specific dependencies.
TypeScript requires a source-checkout `node_modules` in the test's ancestor
directories, linked at the corresponding exported path; npx is offline. Missing
modules yield an explicit rejection. Go uses `GOFLAGS=-mod=mod` and a work-local
`GOCACHE`; `GOPROXY=off`, `GOSUMDB=off`, and `GOTOOLCHAIN=local` prevent downloads.
With `--work-dir`, successive replays share a Go cache inside that directory.
Python imports prefer the archived root and `src/` over host editable installs.
npm uses a temporary cache and ignores the host user configuration.

`verify.py` rederives and checks candidate metadata against pinned Git history,
exports two fresh trees, overlays only the fix's test files onto the parent, and
runs both phases. Each command must fail as a test on the parent and pass on the
fix. A parent build/import failure also qualifies when every diagnostic names a
symbol introduced by the non-test delta (Go also permits changed signatures in
the tested package). Unrelated dependencies, syntax/environment errors, unknown
diagnostics, truncated missing-symbol output, empty runs and timeouts are rejected.
Verified rows record `fails_by: assertion | missing_symbol`, plus the missing names;
selection includes that prerequisite in the task text.
A bash harness uses exit 1 for test failure; its output cannot distinguish every
possible setup error, so harnesses must reserve that code for assertions. Both
phases return command, exit code, timeout flag and up to 12 KB of output tail.
Temporary trees and private Go caches are removed afterward; the explicitly
shared `--work-dir/go-cache` remains available for subsequent runs. Unsafe archive paths and
escaping symlinks are rejected. The source checkout and its Git metadata are
never modified by the scripts (tests themselves must also respect that rule).

`select.py` accepts verification JSONL files, ignores rejected rows, deduplicates
candidates and uses quotas Go 6 / Python 7 / TypeScript 5 / shell 2 (`--quota`
for others). It prefers
less-used repositories, then less-used file paths, with stable commit-based tie
breaking. One fix commit is used at most once, even if it has multiple languages.
Each question includes the parent SHA, fix SHA for retrieving overlay tests,
test paths, check commands and task text. A short pool reports the exact missing
counts per language on stderr and exits 1 without creating or replacing the
output. A complete pool writes a JSON array of 20 questions. Treat the fix SHA
and overlaid tests as evaluator metadata when preparing executor workspaces.

Two more fields (TD-373), from `interface.py`. `interface`: what the selected
tests call that the parent lacks or declares otherwise, each the declaration as
the fix wrote it, headed by where it is: Go through `goapi.go` (`go run`,
standard library: go/ast), Python through `ast`, TypeScript by its exports
(default ones and names handed on by an index's re-exports included), shell
by its new functions and the names of the environment variables it newly
reads; options newly declared by a changed file (a case label, argparse, Go's
flag package) that the tests pass; and the texts the tests compare that the fix
wrote inside a string literal (a message, a key, a query; comments and code are
not texts). Never an answer: no body, no value (a variable is its name and
type, a function value its signature), only the fields of a new struct the
tests use (embedded ones always). Every name `verify.py` found missing is
covered, or the candidate is refused; the bounds are agentd's, in UTF-8 bytes.
agentd bench gives the list to the executor, so a question measures the
change, not a guess at its names. `siblings`: the repositories a TypeScript
package links with `file:../<repo>`, each at its `main` as of the fix's commit
time; agentd bench builds them beside the trees before the checks. The task
text drops the final trailer block and, before it, blocks of this workspace's
known trailers whose values have their forms.

`verify.py` runs on the Mac against the source checkout. Whether a question
stands on the agent host is a separate check: the controls and the fix's own
change through agentd bench's judgement, with nothing but the question's own
repository and its siblings, no test database and no network
(`bifrost-platform/api/internal/agentd/benchreplay_test.go`, build tag
`benchreplay`). A check whose tests all skip there (a test database they lack)
passes on the fix and measures nothing: such a question is not used.
