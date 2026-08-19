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
docker build -t auto-deduct:latest -f Dockerfiles/AutoDeductDockerfile .
```

On Apple Silicon, add `--platform linux/amd64` to build and run commands.

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
  --output-dir examples/ase-2024/autodeduct-output-local \
  examples/ase-2024
```

The local tools must be compatible with the versions expected by the current
branch. If a required executable or plugin is missing, the command reports an
`environment` failure before changing any input file. Docker remains the
reproducible way to obtain the complete matching toolchain.

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
units. Header files are not passed as source inputs; provide additional header
directories with `--include`:

```shell
docker run --rm \
  -v "$PWD":/work \
  -w /work \
  auto-deduct:latest \
  autodeduct \
  --include /work/my-project/include \
  --entry-point main \
  --output-dir /work/my-project/autodeduct-output \
  /work/my-project
```

For explicit source files or several translation units:

The 1.0 image installs `autodeduct`, the CLI pipeline. Experimental
assistant and GUI/LLM workflows from earlier development remain outside this
release profile and are not installed in the V1 image.

The command accepts C source files and project directories. Directory inputs
are searched recursively for `.c` files; common build, VCS, dependency, and
generated-output directories are skipped. Pass `--include` for header
directories that are not next to the source files.
Preprocessor/compiler flags can be passed with repeated
`--frama-c-option`, for example:

```shell
autodeduct \
  --frama-c-option=-cpp-extra-args=-DPLATFORM_TEST \
  --include include \
  src/main.c src/account.c
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
- `examples/ase-2024/`: attributed public steering-system example with an
  entry-point contract.
- `tests/test_autodeduct.py`: pipeline tests that do not require Docker.

## License

AutoDeduct is provided under the GNU GPLv2. See [LICENSE](LICENSE).
