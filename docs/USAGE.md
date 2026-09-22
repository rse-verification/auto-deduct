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

The output directory contains:

- `inferred.c`: functional contracts emitted through Saida/TriCera.
- `out.c`: ISP auxiliary annotations applied to the inferred source.
- `missing-helper-contracts.json`: ISP reachable-contract report.
- `contracts.json`: normalized AutoDeduct contract summary.
- `report.json`: final pipeline and stage status.
- stage-specific stdout and stderr logs.

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
