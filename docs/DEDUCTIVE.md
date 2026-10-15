# Deductive usage

[Documentation index](README.md) · [Setup](INSTALLATION.md) · [Common CLI options](USAGE.md)

This mode runs Frama-C parsing, Saida/TriCera contract inference, ISP/Eva auxiliary
annotation inference, reachable-helper coverage checks, then WP verification.
It is the default; `deductive` and `--mode deterministic` select the same path.

## Run in Docker

After [building the standard image](INSTALLATION.md#standard-docker-image),
run from the AutoDeduct checkout:

```shell
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD":/work -w /work \
  auto-deduct:latest \
  autodeduct deductive --entry-point main \
  --output-dir /work/autodeduct-output \
  /work/examples/ase-2024/stee.c
```

AutoDeduct and all analysis tools execute inside Docker. Host Python and Codex
are unnecessary. On Apple Silicon, add `--platform linux/amd64` after
`docker run`, matching the image build.

For another project, mount its root as `/work`, pass the C file and any headers
with `--include /work/include`. Keep generated output separate from input.
The Bash/WSL command uses your host UID/GID so the container can write output
and you can read its private reports and logs afterwards.

## Run locally

After the [native toolchain setup](INSTALLATION.md#native-installation):

```shell
./bin/autodeduct deductive --entry-point main \
  --output-dir /tmp/deductive-proof examples/ase-2024/stee.c
```

With `bin/` on `PATH`, use `autodeduct` directly. The command requires compatible
Frama-C/Saida/ISP, TriCera and WP provers on the host; Docker is optional.

## Generated files

| File | Purpose |
| --- | --- |
| `inferred.c` | Functional contracts from Saida/TriCera |
| `out.c` | ISP auxiliary annotations applied to the inferred source |
| `missing-helper-contracts.json` | ISP reachable-helper coverage report |
| `contracts.json` | Normalized contract summary |
| `report.json` | Final pipeline and stage status |
| Stage stdout/stderr logs | Component output and proof diagnostics |

Every mandatory stage and every nonzero WP goal must pass. Missing reachable
contracts fail the run even if WP could prove some obligations. `--wp-rte` adds
runtime-error goals; it is disabled by default. See [reports](PIPELINE.md) and
[deductive limitations](LIMITATIONS.md#deductive-inference-boundaries).

## Inspect individual stages

Use this native workflow only after installing the same tools:

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

The public [ASE 2024 example guide](../examples/ase-2024/README.md) records
provenance. [Regression cases](../tests/cases/README.md) document expected
successes, warnings and incomplete proofs.
