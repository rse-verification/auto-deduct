# Usage

AutoDeduct accepts one C source file or a project directory that resolves to
exactly one C translation unit. It writes all generated artifacts to a
separate output directory and does not edit the source project.

## CLI

```text
autodeduct --help
autodeduct --version
autodeduct [options] SOURCE_OR_DIRECTORY [SOURCE_OR_DIRECTORY ...]
```

Common options:

- `--mode deterministic|llm`: contract-generation path; default is deterministic.
- `--entry-point NAME`: contracted entry function; default is `main`.
- `--output-dir DIRECTORY`: generated files and logs; default is
  `autodeduct-output`.
- `--include DIRECTORY`: add a header directory; repeat as needed.
- `--frama-c-option OPTION`: forward an option to Frama-C stages.
- `--wp-option OPTION`: forward an option only to WP.
- `--wp-rte`: add WP runtime-error goals; these are not included by default.
- `--timeout SECONDS`: timeout for each external stage; default is 300.
- `--json`: print the final machine-readable report to standard output.

Pipeline-owned options cannot be overridden through forwarded Frama-C or WP
arguments.

## LLM Mode

This is an experimental integration, not a bundled or turnkey LLM verifier.
The provider must implement the evidence interface below and have its parser
and verification dependencies configured before use.

Configure the installed private skill once:

```shell
export AUTODEDUCT_LLM_SKILL=/opt/contract-provider/skill/SKILL.md
autodeduct --mode llm --timeout 1200 --output-dir /tmp/proof-run src/main.c
```

The same path can be passed as `--llm-skill SKILL_MD`.
In LLM mode, `--timeout` limits the entire external skill workflow, including
model calls and verification. The default 300 seconds may be too short for
larger inputs; `--wp-option=-wp-timeout=30` separately sets WP's prover timeout.
AutoDeduct invokes `codex exec`, explicitly instructs it to read that
SKILL.md, and requests the complete generation, annotation, and verification
workflow. The skill's repository owns the contract semantics, rendering, WP
execution, and its text/PDF reports. AutoDeduct does not run a second WP pass,
Saida/TriCera, or ISP/Eva in this mode. Contract JSON is an internal artifact;
there is no public `--contracts` option.

Install and authenticate Codex CLI separately, and make the private skill and
its verification dependencies available in the runner's environment. Public
AutoDeduct neither clones the private repository nor bundles its contents.
Running LLM mode gives the configured Codex model access to the skill and
input source. Use an account/environment approved for those files.

The default runner is `codex exec`. Override it with
`--llm-runner COMMAND` or `AUTODEDUCT_LLM_RUNNER` for a configured
Codex profile. Commands execute without a shell. Absolute script paths are
required; no credentials should be placed in the command string because it
is retained in the report. AutoDeduct requests a workspace-write sandbox
rooted at the output directory. A configured `--approve-for-me` runner
uses that mode's own workspace-write policy. Permissions are not bypassed;
missing tools or denied actions fail the run.

See the official [non-interactive Codex documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
and [skills documentation](https://learn.chatgpt.com/docs/build-skills).

### Workflow and evidence

AutoDeduct writes `llm-task.json` with absolute paths for the input,
contract JSON, annotated C, verification JSON, and requested verification
options. Codex reads the actual configured skill and uses its repository's
wrapper with `--verify --verification-json FILE`. Each requested
verification option is forwarded using `--frama-c-option=VALUE`.
This includes entry point, include paths, WP options, and `--wp-rte`.

The provider wrapper must emit this version-1 verification JSON directly
from its verifier process (not from the model's final message):

```json
{
  "schema_version": 1,
  "command": ["frama-c", "-main", "main", "-wp", "/absolute/output/inferred.c"],
  "returncode": 0,
  "source_sha256": "<SHA-256 of the annotated C bytes>",
  "stdout": "[wp] Proved goals: 2 / 2\n",
  "stderr": ""
}
```

The command must contain all requested options in order. Extra provider
fields are allowed. The private integration patch adds these CLI/report
options and makes incomplete or zero-goal verification return failure.
An older provider without that patch fails explicitly.

AutoDeduct records `llm_workflow` (the skill execution) and
`skill_verify` (inspection of its evidence, not another proof run).
It checks source/contract hashes, annotation-only changes, the reported
verification command, the process return code, and complete nonzero WP
goals. A successful agent exit or a prose claim alone cannot pass the run.
The skill and its verifier remain trusted components; a JSON report is
verification evidence, not a cryptographically certified proof.

The run directory contains `llm-task.json`, `llm-contracts.json`,
`inferred.c`, `llm-verification.json`, the provider's
`inferred.wp-report.txt`/`.pdf`, agent logs/final text,
extracted verifier logs, and AutoDeduct's `report.json`.
The report records `mode: "llm"` and `contract_report: null`.
The output directory must be separate from the input source and skill files.

The example private skill currently requires existing ACSL in its input.
Its parser depends on libclang; the fallback misses some function forms,
including the tested `static inline` case. Forwarded include/macro options
apply to verification, not automatically to its annotation parser.
Existing specifications are preserved, and only ACSL block insertions
between original source lines are accepted. Loops may need explicit
invariants. LLM mode provides no ISP reachability-coverage guarantee.
Proof success is relative to the supplied specifications and assumptions,
not a guarantee that the model captured all intended requirements.

## Docker

Mount the project or repository containing it as `/work`:

```shell
docker run --rm \
  -v "$PWD":/work \
  -w /work \
  auto-deduct:latest \
  autodeduct \
  --entry-point main \
  --output-dir /work/autodeduct-output \
  /work/examples/ase-2024
```

Add `--platform linux/amd64` after `docker run` on Apple Silicon.

For headers outside the source directory:

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

## Without Docker

After completing the native setup in [Installation](INSTALLATION.md):

```shell
export PATH="$PWD/bin:$PATH"
autodeduct \
  --entry-point main \
  --output-dir autodeduct-output \
  examples/ase-2024
```

The checkout-local command also works without changing `PATH`:

```shell
./bin/autodeduct --entry-point main examples/ase-2024
```

## Input Rules

Directory inputs are searched recursively for `.c` and `.C` files. Common
build, version-control, dependency, and generated-output directories are
ignored. Header files are not source inputs; provide their locations with
`--include`.

AutoDeduct 1.0 Saida inference accepts one translation unit. A directory containing
multiple C translation units is rejected instead of silently processing only
one. Such a project must first be represented as one analysis translation
unit.

Preprocessor macros can be forwarded explicitly:

```shell
autodeduct \
  --frama-c-option=-cpp-extra-args=-DPLATFORM_TEST \
  --include include \
  src/main.c
```

## Generated Output

In deterministic mode, the output directory contains:

- `inferred.c`: functional contracts emitted through Saida/TriCera.
- `out.c`: ISP auxiliary annotations applied to the inferred source.
- `missing-helper-contracts.json`: ISP reachable-contract report.
- `contracts.json`: normalized AutoDeduct contract summary.
- `report.json`: final pipeline and stage status.
- stage-specific stdout and stderr logs.

LLM mode instead retains skill-generated contracts, annotated C, verification
reports, agent and verifier logs, and AutoDeduct's `report.json`.
The report records `mode: "llm"` and `contract_report: null`; it does not claim
ISP contract coverage. No automatic fallback between modes takes place.

Old known artifacts are invalidated at the start of a valid run so a previous
successful report cannot be mistaken for the current result. The output
directory may not overlap the source tree.

## Run Stages Manually

This native workflow is useful for inspecting intermediate output:

```shell
PROJECT="$PWD/examples/ase-2024"
OUT="$PWD/autodeduct-output-manual"
mkdir -p "$OUT"
cd "$OUT"
CPP_INCLUDE="-cpp-extra-args=-I$PROJECT"

frama-c -main main "$CPP_INCLUDE" "$PROJECT/stee.c"

frama-c -main main "$CPP_INCLUDE" \
  -saida -saida-tricera-path tri \
  "-saida-out=$OUT/inferred.c" "$PROJECT/stee.c"

frama-c -main main "$CPP_INCLUDE" \
  -isp-entry-point main -isp \
  -isp-missing-helper-contracts \
  -isp-missing-helper-contracts-json "$OUT/missing-helper-contracts.json" \
  "$OUT/inferred.c" -isp-print-file "$OUT/out.c"

frama-c -main main "$CPP_INCLUDE" -wp "$OUT/out.c"
```

See [Pipeline and diagnostics](PIPELINE.md) for how each result contributes to
the final status.
