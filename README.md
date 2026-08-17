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

Saida invokes TriCera to infer functional contracts below a contracted entry
point. ISP consumes that annotated source and uses Eva-derived states to infer
auxiliary ACSL clauses. AutoDeduct relies on ISP's reachable-function report
for missing-contract checks rather than maintaining a separate call graph.

## Build the Docker Image

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

## Repository Layout

- `bin/autodeduct`: executable CLI entry point.
- `bin/autodeduct_pipeline.py`: argument parsing, stage execution, contract
  reachability checks, and report generation.
- `Dockerfiles/AutoDeductDockerfile`: Frama-C/Saida/TriCera/ISP environment.
- `tests/test_autodeduct.py`: pipeline tests that do not require Docker.

## License

AutoDeduct is provided under the GNU GPLv2. See [LICENSE](LICENSE).
