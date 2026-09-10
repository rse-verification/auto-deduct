# AutoDeduct

AutoDeduct 1.0 is a command-line formal-verification pipeline for C programs.
It combines Frama-C, Saida, TriCera, ISP/Eva, and WP to infer contracts and
auxiliary annotations, then checks whether the selected input can be proved.

AutoDeduct never changes the input source. Generated C files, diagnostics,
logs, and the final JSON report are written to a separate output directory.

## Pipeline

```text
C source
   |
   v
Frama-C parse
   |
   v
Saida -> TriCera       functional-contract inference
   |
   v
ISP + Eva              auxiliary-annotation inference
   |
   v
ISP contract check     reachable helpers have contracts
   |
   v
Frama-C WP             proof obligations
   |
   v
console summary + report.json
```

Warnings are retained in the result and normally allow later stages to run. A
successful result still requires all mandatory stages, complete
reachable-helper contract coverage, and all WP goals to pass. See
[Pipeline and diagnostics](docs/PIPELINE.md) for the status rules.

## Quick Start With Docker

```shell
git clone https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
docker build -t auto-deduct:latest -f Dockerfiles/AutoDeductDockerfile .
docker run --rm \
  -v "$PWD":/work \
  -w /work \
  auto-deduct:latest \
  autodeduct --entry-point main examples/ase-2024
```

On Apple Silicon, add `--platform linux/amd64` to both Docker commands.

## Quick Start Without Docker

This requires compatible host installations of Frama-C, Saida, TriCera, ISP,
and the WP provers.

```shell
export PATH="$PWD/bin:$PATH"
autodeduct \
  --entry-point main \
  --output-dir autodeduct-output \
  examples/ase-2024
```

## Documentation

- [Installation](docs/INSTALLATION.md): Docker, native prerequisites,
  component versions, Apple Silicon, and proxy builds.
- [Usage](docs/USAGE.md): CLI options, accepted inputs, generated files,
  Docker/native examples, and individual-stage commands.
- [Pipeline and diagnostics](docs/PIPELINE.md): component responsibilities,
  warnings, failures, logs, and acceptance criteria.
- [Limitations](docs/LIMITATIONS.md): unsupported patterns, diagnostic
  boundaries, and recommended workarounds.
- Public regression tests under `tests/cases/`: supported cases, expected
  warnings, expected limitations, and known incomplete WP outcomes.

## Public Example

`examples/ase-2024/` contains the public steering-system example associated
with the ASE 2024 paper *An Exercise in Mind Reading: Automatic Contract
Inference for Frama-C*. It is copied from the public
[auto-deduct-examples](https://github.com/rse-verification/auto-deduct-examples/tree/main/ase-2024)
repository with attribution. It contains no Scania or private case-study code.
See [the example README](examples/ase-2024/README.md) for provenance and its
dedicated command.

## License

AutoDeduct is provided under the GNU GPLv2. See [LICENSE](LICENSE).
