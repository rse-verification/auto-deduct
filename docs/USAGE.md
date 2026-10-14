# Usage

AutoDeduct accepts one C source file or a project directory that resolves to
exactly one C translation unit. It writes all generated artifacts to a
separate output directory and does not edit the source project.

## CLI

```text
autodeduct --help
autodeduct --version
autodeduct deductive [options] SOURCE_OR_DIRECTORY
autodeduct llm [options] SOURCE_OR_DIRECTORY
autodeduct [options] SOURCE_OR_DIRECTORY [SOURCE_OR_DIRECTORY ...]
```

Common options:

- `--mode deterministic|llm`: contract-generation path; default is deterministic.
  These flags are alternatives to the `deductive` and `llm` command names;
  choose one form. Reports retain `mode: "deterministic"` for the deductive mode.
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

LLM mode uses the [LOGOS](https://github.com/rse-verification/logos) skill for
host Codex contract generation. AutoDeduct explicitly invokes the LOGOS Python
wrapper afterwards to annotate and verify; the model does not run verification.
See [Installation](INSTALLATION.md#logos-for-llm-mode) for the compatible revision.

```shell
export AUTODEDUCT_LLM_SKILL=/absolute/path/to/logos/skill/SKILL.md
# Fully local; Python/libclang/Frama-C/WP/provers and Codex on the host:
autodeduct llm --llm-runtime local --timeout 1200 --output-dir /tmp/proof-run path/to/program.c
# Host Python/Codex, wrapper and verification tools in Docker:
autodeduct llm --llm-runtime docker --timeout 1200 --output-dir /tmp/proof-run path/to/program.c
```

`local` is the default. Docker is optional and never started automatically by
selecting LLM mode alone. `--llm-skill SKILL_MD` overrides the skill environment
variable. Global skill installation is unnecessary; the complete skill directory
must be readable on the host. Build the Docker image from that same checkout.
Running LLM mode sends source/specifications to the configured Codex model.

`--timeout` limits each external stage independently (host generation and wrapper
verification). `--wp-option=-wp-timeout=30` sets WP's individual prover timeout.
Saida/TriCera, ISP/Eva and their helper-coverage check do not run in LLM mode.

`--llm-docker-image IMAGE` selects the verifier image (default `auto-deduct:logos`).
`--llm-docker-platform PLATFORM` selects its platform (default `linux/amd64`).
Docker mode supports Linux/macOS and Windows through WSL. Launching the Codex
workflow inside a container is unsupported and rejected. Codex uses the host
login; no authentication or model credentials are mounted into the verifier.

The default host runner is `codex exec`. `--llm-runner COMMAND` or
`AUTODEDUCT_LLM_RUNNER` can select a Codex profile. These commands receive
Codex-specific arguments; other agents or model APIs need an adapter. Commands
execute without a shell; script paths must be absolute. Do not put credentials
in the command because it is retained in the report. Codex uses a workspace-write
sandbox rooted at the output directory; `--approve-for-me` uses its own automatic
approval policy. The agent writes contract JSON only. Docker is invoked by the
launcher after the agent exits, outside the agent's sandbox.

### Workflow and evidence

AutoDeduct writes `llm-task.json` with absolute paths for the input,
contract JSON, annotated C, verification JSON, and requested verification
options, with `workflow: "generate-only"`. Codex reads the skill and writes only
contract JSON with the matching source hash. AutoDeduct validates that JSON,
then invokes the wrapper locally or inside Docker with
`--verify --verification-json FILE`. Each requested
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
fields are allowed. LOGOS records the actual process exit code in `returncode`
and the proof outcome in `verified`. Its wrapper returns nonzero for incomplete,
missing, or zero-goal summaries, even when Frama-C itself exits zero.
Older LOGOS revisions without these CLI/report options are incompatible.

AutoDeduct records `llm_workflow` (host contract generation), `logos_verify`
(wrapper annotation and verification) and `skill_verify` (evidence validation).
It checks source/contract hashes, annotation-only changes, the reported
verification command, the process return code, and complete nonzero WP
goals. A successful agent exit or a prose claim alone cannot pass the run.
The LOGOS wrapper and its verifier remain trusted components; a JSON report is
verification evidence, not a cryptographically certified proof.

The run directory contains `llm-task.json`, `llm-contracts.json`,
`inferred.c`, `llm-verification.json`, the provider's
`inferred.wp-report.txt`/`.pdf`, agent logs/final text,
extracted verifier logs, and AutoDeduct's `report.json`.
The report records `mode: "llm"` and `contract_report: null`.
The output directory must be separate from the input source and skill files.

LOGOS currently requires existing ACSL in its input.
Its parser requires libclang and reports a dependency error if it cannot load it.
Forwarded include/macro options
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
