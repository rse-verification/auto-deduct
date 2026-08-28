# AutoDeduct

AutoDeduct 1.0 is a command-line formal-verification pipeline for C programs.
It combines Frama-C, Saida, TriCera, ISP/Eva, and WP to infer contracts and
auxiliary annotations and then attempt a complete proof.

The 1.0 release ships the deterministic CLI pipeline only. It does not modify
the original C source files; generated contracts, annotations, logs, and the
final JSON report are written to a separate output directory.

## Pipeline

```text
C source files
      |
      v
Frama-C parse
      |
      v
Saida -> TriCera functional-contract inference
      |
      v
ISP + Eva auxiliary-annotation inference
      |
      v
ISP reachable-contract report
      |
      v
Frama-C WP verification
      |
      v
text summary + report.json
```

Saida is the Frama-C plugin that invokes TriCera to infer functional
contracts for helper functions below a contracted entry point. ISP consumes
that annotated C source and uses Eva-derived states to infer auxiliary ACSL
clauses for WP. ISP also owns the reachable-function analysis: AutoDeduct
passes ISP's `-isp-missing-helper-contracts` options through Frama-C and reads
the resulting `missing-helper-contracts.json`. AutoDeduct does not reimplement
the C parser or call graph, so function reachability and missing-contract
semantics stay aligned with ISP. A missing reachable contract makes the final
pipeline status `failed` even when a later command happens to exit zero.

## Public ASE 2024 example

The repository includes the public steering-system example under
`examples/ase-2024/`. The source is copied from the
[rse-verification/auto-deduct-examples](https://github.com/rse-verification/auto-deduct-examples/tree/main/ase-2024)
repository and retained with its attribution.

The example is associated with the ASE 2024 paper *An Exercise in Mind
Reading: Automatic Contract Inference for Frama-C*:
<https://doi.org/10.1007/978-3-031-55608-1_13>.

`stee.c` models a vehicle steering system. Its ACSL contract is attached to
the entry point `main` and expresses five requirements about primary steering
failure, vehicle movement, secondary steering, and electric-motor activation.
The helper functions are intentionally left without complete contracts so the
toolchain can infer them. See `examples/ase-2024/README.md` for provenance and
the Docker command. No Scania or private case-study files are included.

## Build the Docker image

Build from the repository root:

```shell
git clone https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
docker build \
  -t auto-deduct:1.0.0 \
  -t auto-deduct:latest \
  -f Dockerfiles/AutoDeductDockerfile .
```

On Apple Silicon, build and run the image as `linux/amd64` so the TriCera
preprocessing helper runs with its supported architecture:

```shell
docker build --platform linux/amd64 \
  -t auto-deduct:latest \
  -f Dockerfiles/AutoDeductDockerfile .
```

Behind a proxy, add the build arguments used by the image:

```shell
docker build \
  --build-arg PROXY_HOST=<proxy-host> \
  --build-arg PROXY_PORT=<proxy-port> \
  -t auto-deduct:latest \
  -f Dockerfiles/AutoDeductDockerfile .
```

The Dockerfile accepts `SAIDA_REPO`, `TRICERA_REPO`, and `ISP_REPO` repository
URL arguments, plus `SAIDA_VER`, `TRICERA_VER`, and `ISP_VER` ref arguments.
Each ref may be a branch, tag, or commit reachable from its selected
repository. The repository defaults and component refs are unchanged. For
example, to test approved component fixes without changing the CLI:

```shell
docker build \
  --build-arg SAIDA_VER=<saida-branch-tag-or-commit> \
  --build-arg TRICERA_VER=<tricera-branch-tag-or-commit> \
  --build-arg ISP_VER=<isp-branch-tag-or-commit> \
  -t auto-deduct:component-test \
  -f Dockerfiles/AutoDeductDockerfile .
```

For a fix that exists only in a fork, provide that repository URL together
with its branch or commit:

```shell
docker build \
  --build-arg TRICERA_REPO=https://github.com/<user>/tricera.git \
  --build-arg TRICERA_VER=<branch-or-commit> \
  -t auto-deduct:component-fork-test \
  -f Dockerfiles/AutoDeductDockerfile .
```

The image checks out each requested ref in detached-head mode, so a moving
branch is resolved to the commit fetched during the build. The resolved
commit is also stored in `REVISION` inside each component checkout under
`/home/dev/repos/` (`saida/REVISION`, `tricera/REVISION`, and
`interface-specification-propagator/REVISION`). Replace the placeholders only
with refs that exist in the relevant upstream repository; this repository does
not hard-code unapproved component-fix refs.

For reproducible release images, use immutable commit hashes. Docker may reuse
a cached checkout when the same mutable branch name is rebuilt after that
branch moves. Add `--no-cache` when deliberately retesting a moving branch.

The image contains configured versions of Frama-C, Saida, ISP, and TriCera.
The image also contains the SMT solvers used by WP. The image is optional: the
same `bin/autodeduct` command can run on a host where the matching tools and
their dependencies are already installed.

## Run the CLI without Docker

Docker is optional. A host installation must already provide Python 3.10 or
newer, Frama-C with the Saida and ISP plugins installed, the TriCera `tri`
executable, and the SMT solvers used by WP. The Python CLI has no additional
package dependencies.

From the repository root, make the local command available on `PATH`:

```shell
chmod +x bin/autodeduct
export PATH="$PWD/bin:$PATH"
```

Check the required host tools before running the pipeline:

```shell
python3 --version
command -v frama-c
command -v tri
frama-c -plugins | grep -Ei "saida|isp"
```

Run the public ASE 2024 example directly on the host:

```shell
autodeduct \
  --entry-point main \
  --output-dir autodeduct-output-ase-2024-local \
  examples/ase-2024
```

Alternatively, invoke the checkout-local executable directly without adding
`bin/` to `PATH`:

```shell
./bin/autodeduct \
  --entry-point main \
  --output-dir autodeduct-output-ase-2024-local \
  examples/ase-2024
```

The local tools must be compatible with the versions expected by the current
branch. If a required executable or plugin is missing, the command reports an
`environment` failure before changing any input file. Docker remains the
reproducible way to obtain the complete matching toolchain.

## Run the stages manually without Docker or the AutoDeduct CLI

The `autodeduct` wrapper is optional. If the matching tools are installed on
the host, each pipeline stage can also be run directly. This is useful for
debugging one stage at a time or inspecting its intermediate output. The V1
release has no GUI, so this manual workflow is still command-line based.

From the repository root, run the following example:

```shell
PROJECT="$PWD/examples/ase-2024"
OUT="$PWD/autodeduct-output-manual"
mkdir -p "$OUT"
cd "$OUT"
CPP_INCLUDE="-cpp-extra-args=-I$PROJECT"

# 1. Parse the source with Frama-C.
frama-c -main main "$CPP_INCLUDE" "$PROJECT/stee.c"

# 2. Infer functional contracts with Saida and TriCera.
frama-c -main main "$CPP_INCLUDE" \
  -saida -saida-tricera-path tri \
  "-saida-out=$OUT/inferred.c" "$PROJECT/stee.c"

# 3. Infer auxiliary annotations with ISP and Eva.
frama-c -main main "$CPP_INCLUDE" \
  -isp-entry-point main -isp \
  -isp-missing-helper-contracts \
  -isp-missing-helper-contracts-json "$OUT/missing-helper-contracts.json" \
  "$OUT/inferred.c" -isp-print-file out.c

# 4. Verify the generated source with WP.
frama-c -main main "$CPP_INCLUDE" -wp "$OUT/out.c"
```

The intermediate files are written to `autodeduct-output-manual/`:

* `inferred.c` is Saida's functional-contract output.
* `out.c` is ISP's auxiliary-annotation output.
* `missing-helper-contracts.json` is ISP's reachable-contract report.

V1 Saida inference accepts exactly one C translation unit. Use additional
`-cpp-extra-args=-I/path/to/include` arguments for its header directories.
Projects requiring multiple `.c` inputs must first be represented as one
analysis translation unit; AutoDeduct rejects them instead of silently
processing only the first file.

## Run the CLI in Docker

```shell
docker run --rm \
  -v "$PWD":/work \
  -w /work \
  auto-deduct:latest \
  autodeduct --entry-point main path/to/main.c
```

Use `--include` for header directories, `--output-dir` for generated artifacts,
and `--json` for machine-readable reporting. The V1 pipeline accepts one C
translation unit plus its headers.

For a project directory, AutoDeduct recursively discovers `.c` translation
units and requires exactly one. Header files are not passed as source inputs;
provide additional header directories with `--include`:

```shell
docker run --rm \
  -v "$PWD":/work \
  -w /work \
  auto-deduct:latest \
  autodeduct \
  --include /work/my-project/include \
  --entry-point main \
  --output-dir /work/autodeduct-output \
  /work/my-project
```

The command accepts one C source file or a project directory containing one C
translation unit. Directory inputs are searched recursively for `.c` files;
common build, VCS,
dependency, and generated-output directories are skipped. Pass `--include` for
header directories that are not next to the source files. The output directory
must be outside the input source tree, so generated artifacts cannot overwrite
the project being analysed.
Preprocessor/compiler flags can be passed with repeated
`--frama-c-option`, for example:

```shell
autodeduct \
  --frama-c-option=-cpp-extra-args=-DPLATFORM_TEST \
  --include include \
  src/main.c
```

## CLI options

```text
autodeduct --help
autodeduct --version
autodeduct [options] SOURCE_OR_DIRECTORY [SOURCE_OR_DIRECTORY ...]
```

Useful options are `--entry-point`, `--output-dir`, `--include`,
`--frama-c-option`, `--wp-option`, `--wp-rte`, `--timeout`, and `--json`.
The output directory contains `inferred.c`, `out.c`,
`missing-helper-contracts.json`, stage logs, and `report.json`.

* `--entry-point NAME` selects the contracted entry function; default is
  `main`.
* `--output-dir DIRECTORY` stores generated files and logs; default is
  `autodeduct-output`.
* `--include DIRECTORY` adds a C include directory and can be repeated.
* `--frama-c-option OPTION` forwards an option to the Frama-C stages and can
  be repeated.
* `--wp-option OPTION` forwards an option only to WP and can be repeated.
* `--wp-rte` adds WP runtime-error goals.
* `--timeout SECONDS` limits each external analysis stage; default is 300. The
  value must be finite and greater than zero.
* `--json` prints the final machine-readable report to standard output.

Forwarded options cannot replace the pipeline-owned entry point or activate,
disable, or reconfigure the Saida, ISP, and WP stages. Use AutoDeduct's
dedicated CLI options for those controls.

The output directory contains `inferred.c` from Saida, `out.c` from ISP,
`contracts.json` (AutoDeduct's normalized summary),
`missing-helper-contracts.json` from ISP, one stdout and stderr log per stage,
and `report.json`. The ISP missing-helper report is required; if ISP does not
write valid JSON with a supported missing-contract field, the pipeline fails
at `contract-check` with an actionable error.

Once the requested output path is known to be separate from the input, an old
`report.json` is invalidated before source validation. This prevents a failed
invocation from leaving a previous `passed` report for automation to consume.
AutoDeduct also treats a WP run with no proof goals as a failure rather than a
successful verification.

If the requested output overlaps an input tree, AutoDeduct deliberately leaves
that location untouched and reports the validation failure on the console (or
standard output with `--json`). This preserves the stronger rule that source
trees are never cleaned or rewritten by the runner.

## Result and failure handling

The CLI returns exit code `0` only when parsing, functional inference,
auxiliary annotation inference, reachable-contract checking, and WP all pass.
It returns exit code `1` for input, environment, timeout, parsing, inference,
annotation, contract, or WP failures. `--json` writes the same stage status,
command, logs, artifacts, and error information in machine-readable form.

## Repository layout

- `bin/autodeduct`: executable CLI entry point.
- `bin/autodeduct_pipeline.py`: stage execution, ISP report handling, and
  report generation.
- `Dockerfiles/AutoDeductDockerfile`: Frama-C/Saida/TriCera/ISP environment.
- `examples/ase-2024/`: attributed public steering-system example with an
  entry-point contract.
- `tests/test_autodeduct.py`: pipeline tests that do not require Docker.

The underlying plugins remain experimental. In particular, ISP does not yet
support recursive auxiliary annotation generation for nested alternating
array/struct paths such as `records[slot].f1[i].f2[j]`. For this pattern, ISP
reports `ISP-E010` and AutoDeduct fails the `isp_eva` stage rather than
presenting generated output as a complete proof.
The human report names the failing stage. `--json` is intended for CI and
skill integrations; it contains the same stage status, command, return code,
log paths, artifacts, contract reachability, and error information.

The command does not treat a process exit code as proof that the complete
contract was verified. It also checks that Saida and ISP produced their
expected generated files and that ISP reports contracts for all functions it
considers reachable from the entry point.

Input diagnostics are reported before analysis when a source path does not
exist, is not a regular file or directory, or is an explicit source file with
an unsupported suffix. Directory inputs must contain at least one discoverable
`.c` translation unit, and V1 requires the resolved input to contain
exactly one translation unit because Saida's source merge is not file-aware.
Header files should be supplied through `--include` rather than as source
inputs. If Frama-C reports that the selected
entry point is not defined,
AutoDeduct identifies the missing function and suggests checking
`--entry-point`. If a source calls a function without a visible forward
declaration, the parse error explains that a prototype must be added in the
source or an included header. AutoDeduct removes only its known generated files
and stage logs at the start of a run, preventing artifacts from an earlier run
from being mistaken for current output while preserving unrelated files.
When WP leaves goals unresolved, the failure reports the proved/total count
and includes the unresolved goal status and name when WP prints them.

## V1 scope and limitations

V1 is a deterministic CLI pipeline. It does not modify source files or
automatically accept generated contracts into the original project.

### Diagnostic policy

The underlying Saida, TriCera, and ISP plugins are experimental and retain
their own limitations. AutoDeduct classifies a limitation only from explicit
stage output, native plugin diagnostic codes, and unresolved WP obligations.
It does not search C source text with regular expressions to guess which
language feature caused a failure. This keeps diagnostics reproducible and
avoids claiming a source-level cause that the analysis tools did not establish.

The Saida/TriCera stage fails even when its process exits with status zero if a
diagnostic-form log line reports `Syntax Error`, `Not solvable`, or that a type
is not supported. A diagnostic-form line may have Frama-C/plugin and severity
prefixes, but the diagnostic phrase must begin the remaining line; incidental
prose containing the same words is ignored. AutoDeduct does not accept
TriCera's integer fallback for `float`, `double`, `long double`, or any other
unsupported type as verification of the source semantics.

ISP diagnostic `ISP-E005` is reported as an unsupported lvalue, pointer, or
array-index boundary and stops the pipeline before WP. AutoDeduct includes the
native ISP detail because the same code covers several expression shapes,
including pointer arithmetic, nested pointer dereferences, and non-lvalue
indexes. All `ISP-Wxxx` diagnostics also stop the pipeline before WP because
ISP documents them as evidence of partial auxiliary inference.

When WP leaves explicit loop-invariant, loop-assigns, or loop-variant goals
unresolved, or reports a missing loop annotation, AutoDeduct names the loop
boundary in its final message. It still reports the proved/total goal count.
A completed process with unresolved WP goals remains a failed AutoDeduct run.
Some loop cases produce only generic evidence such as `Missing assigns clause`
and function-level `_assigns`, `_signed_overflow`, `_ensures`, or `_terminates`
goals. Those signals also occur in non-loop verification failures, so
AutoDeduct deliberately keeps the WP message generic rather than guessing that
the loop is the cause. Inspect the WP log and add suitable loop annotations
when the source contains a loop.

### Known hard boundaries and workarounds

| Boundary | V1 behavior | Recommended workaround |
| --- | --- | --- |
| Floating point | Fails at `saida_tricera` when TriCera reports an unsupported floating-point type; V1 never accepts the integer fallback as verification. | Use a reviewed fixed-point model or verify floating-point semantics with a toolchain that models the required IEEE behavior. |
| Pointer arithmetic and unsupported lvalue/index expressions | `ISP-E005` preserves the native detail in an actionable `isp_eva` failure and WP is not run. | Simplify the access pattern or provide and review the required validity, separation, frame, and value-relation ACSL manually. |
| Nested pointers | May fail as `ISP-E005`, a Saida/TriCera diagnostic, a missing contract, or unresolved WP goals. V1 does not infer the required multi-level validity and aliasing model. | Flatten the interface where appropriate, or write explicit contracts for every dereference level and review aliasing assumptions. |
| Persistent local static state | There is no stable component diagnostic that identifies every case. AutoDeduct fails if WP is incomplete, but it does not infer persistence semantics or guess this cause from source text. | Model the persistent state explicitly and give the function an accurate frame and state-transition contract. Do not use `assigns \nothing` for a function that changes static state. |
| Loops | Unresolved or missing loop annotations produce a specific WP failure when WP identifies them. General loop-invariant inference is outside V1. | Add and review `loop invariant` and `loop assigns` clauses, plus `loop variant` when termination must be proved. |

The absence of one of these specific messages does not mean the corresponding
feature is supported. Some component versions emit only a generic syntax,
inference, missing-contract, or WP failure. Always retain and inspect the stage
logs named in `report.json` when qualifying a new input pattern.

The V1 pipeline accepts one C translation unit plus its headers; multiple `.c`
inputs fail before tool execution. Saida accepts the
documented C-expression subset of `requires`, `ensures`, and supported
behavior guards; general ACSL logic functions and predicates are outside this
inference subset. Behavior-specific `assigns`, `complete`, and `disjoint`
clauses are rejected rather than silently omitted.
Saida preserves function-level `assigns` clauses but its inference harness
does not itself prove their frame conditions; `SAIDA-W001` identifies that
partial check, and AutoDeduct relies on the final WP stage before reporting a
successful complete-contract result.

ISP does not currently support recursive auxiliary annotation generation for
arrays contained in struct fields, such as repeated paths of the form
`records[slot].f1[i].f2[j]`. The merged enum-indexed struct support covers
flat struct fields after an enum-indexed array access, not arbitrary nested
`Field -> Index` paths. ISP also rejects an array index that Eva cannot bound
to integer values, or whose concrete expansion would exceed 1024 values,
rather than risking a crash or an impractically large generated contract.

For this unsupported nested-aggregate pattern, ISP reports diagnostic
`ISP-E010` and the AutoDeduct `isp_eva` stage fails clearly. This means the
pipeline result is not complete or valid for WP; review the input and
contract manually rather than treating generated output as a proof. AutoDeduct
does not modify the original source files.

Unbounded or excessively wide Eva-resolved indexes report `ISP-E011` with the
same fail-closed pipeline behavior.

A successful command is evidence for the selected input and tool versions,
not a universal proof that every possible execution is safe.

## Repository layout

* `bin/autodeduct` is the small executable entry point.
* `bin/autodeduct_pipeline.py` contains argument parsing, stage execution,
  ISP report handling, and report generation. It deliberately does not
  maintain a second C parser or call graph.
* `Dockerfiles/AutoDeductDockerfile` builds the Frama-C/Saida/TriCera/ISP
  environment and installs the CLI as `autodeduct`.
* `examples/ase-2024/` contains the attributed public steering-system example
  and its entry-point contract.
* `tests/test_autodeduct.py` tests ISP report parsing and orchestration behavior
  without requiring Docker or the analysis tools.

## License

AutoDeduct is provided under the GNU GPLv2. See [LICENSE](LICENSE).
