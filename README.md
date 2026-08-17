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

## Public paper example

The repository includes one public teaching example under
`examples/paper-1046/`. It is based on the CruiseControl code published with
Liu et al., *An Empirical Study of the Code Generation of Safety-Critical
Software Using LLMs*, *Applied Sciences* 14(3), 1046 (2024):
<https://doi.org/10.3390/app14031046>.

The public source is kept unchanged and is accompanied by its original
license notice. The separate `harness.c` file adds an ACSL entry contract for
AutoDeduct; it does not modify the paper source. This example uses only the
standard `<stdio.h>` header and contains no Scania or private case-study
files. See `examples/paper-1046/README.md` for provenance and the Docker
command.

## Build the Docker image

Build from the repository root:

```shell
git clone https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
docker build -t auto-deduct:latest -f Dockerfiles/AutoDeductDockerfile .
```

On Apple Silicon, add `--platform linux/amd64` to build and run commands.

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

## Release Scope

The 1.0 image installs `autodeduct`, the CLI pipeline. Experimental contract-
assistant and GUI/LLM workflows from earlier development remain outside this
release profile and are not installed in the V1 image.

## CLI Options

```text
autodeduct --help
autodeduct --version
autodeduct [options] SOURCE.c [SOURCE.c ...]
```

Useful options are `--entry-point`, `--output-dir`, `--include`,
`--frama-c-option`, `--wp-option`, `--wp-rte`, `--timeout`, and `--json`.
The output directory contains `inferred.c`, `out.c`,
`missing-helper-contracts.json`, stage logs, and `report.json`.

## Result and Failure Handling

The CLI returns exit code `0` only when parsing, functional inference,
auxiliary annotation inference, reachable-contract checking, and WP all pass.
It returns exit code `1` for input, environment, timeout, parsing, inference,
annotation, contract, or WP failures. `--json` writes the same stage status,
command, logs, artifacts, and error information in machine-readable form.

## Repository Layout

- `bin/autodeduct`: executable CLI entry point.
- `bin/autodeduct_pipeline.py`: stage execution, ISP report handling, and
  report generation.
- `Dockerfiles/AutoDeductDockerfile`: Frama-C/Saida/TriCera/ISP environment.
- `examples/paper-1046/`: attributed public paper example and harness.
- `tests/test_autodeduct.py`: pipeline tests that do not require Docker.

## License

AutoDeduct is provided under the GNU GPLv2. See [LICENSE](LICENSE).
