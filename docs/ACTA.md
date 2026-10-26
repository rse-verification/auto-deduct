# AcTa and CBMC

[Documentation index](README.md) · [Common usage](USAGE.md) · [Installation](INSTALLATION.md)

`autodeduct acta` calls [AcTa](https://github.com/rse-verification/AcTa), which
generates a harness from an existing entry contract, runs
[CBMC](https://github.com/diffblue/cbmc), and writes its verification report.
AutoDeduct imports that report into its common result format. It accepts one C
translation unit and its headers. The entry needs an `ensures` clause.
Implemented helpers are analyzed by CBMC through their bodies; no helper
contracts need to be inferred first.

For AcTa's implementation, build instructions and standalone CLI, see the
[upstream repository](https://github.com/rse-verification/AcTa#readme).
This guide covers its integration with AutoDeduct.

## Docker from the host launcher

Build or load the optional `auto-deduct-acta-runtime` image first. It extends
the standard image with AcTa, its Frama-C frontend, and CBMC. There is no host AcTa,
Frama-C, CBMC, Codex or LOGOS installation requirement for this workflow.
Host Python 3.10+ and Docker are required. Use WSL 2 on Windows.

AcTa is currently a private repository. Your account needs read access.
With GitHub CLI authenticated, build from the AutoDeduct checkout:

```shell
GH_TOKEN="$(gh auth token)" docker build --platform linux/amd64 \
  --secret id=github_token,env=GH_TOKEN \
  --target auto-deduct-acta-runtime -t auto-deduct:acta \
  -f Dockerfiles/AutoDeductDockerfile .
```

The token is used through a temporary BuildKit secret. It is not passed as a
build argument or embedded in Git URLs, image layers or the runtime environment.
For a publicly accessible AcTa fork, the secret can be omitted and the build
can select its repository/ref through `ACTA_REPO` and `ACTA_VER`. The default
public image target is unchanged and does not require AcTa access.

Then run:

```shell
./bin/autodeduct acta examples/acta/increment.c \
  --entry-point compute --acta-runtime docker \
  --acta-docker-image auto-deduct:acta \
  --output-dir /tmp/autodeduct-acta --json
```

As with LOGOS Docker mode, the launcher resolves the installed image to its
immutable ID, disables container networking, mounts source/header directories
read-only, mounts the output directory writable, and runs with the host UID/GID.
It stops verifier containers on failure or timeout. It never builds or pulls
images automatically. Select a custom image with `--acta-docker-image NAME:TAG`
and its architecture with `--acta-docker-platform PLATFORM` (default
`linux/amd64`).

## CLI inside Docker

You can also run the whole AcTa workflow inside an existing image. The default
`--acta-runtime local` then refers to the tools installed inside that container:

```shell
mkdir -p /tmp/autodeduct-acta
docker run --rm --platform linux/amd64 --network none \
  -v "$PWD:/work:ro" -v /tmp/autodeduct-acta:/output -w /work \
  auto-deduct:acta autodeduct acta examples/acta/increment.c \
  --entry-point compute --output-dir /output --json
```

Do not select `--acta-runtime docker` inside a container; launch that form on
the host instead.

## Without Docker

Install Python 3.10+, the AutoDeduct launcher, a compatible AcTa/Frama-C
installation, CBMC, and a C preprocessor on the local PATH. The pinned AcTa
revision requires Frama-C 31.x. Keep it in a separate opam switch if you also
use AutoDeduct's Frama-C 33 toolchain.

Build and install the report-enabled AcTa revision using its
[upstream instructions](https://github.com/rse-verification/AcTa/tree/autodeduct-adoptation#build).
The Docker image pins revision `cbfedef2058bf101a35361a3c9cd0d5d5215f5b4`.
If using a separate opam switch, select its frontend for AutoDeduct:

```shell
eval "$(opam env --switch=acta --set-switch)"
export AUTODEDUCT_ACTA_FRAMA_C="$(opam var bin)/frama-c"
```

Install CBMC from its [official releases](https://github.com/diffblue/cbmc/releases/tag/cbmc-6.11.0).
Then, from the AutoDeduct checkout:

```shell
./bin/autodeduct acta examples/acta/increment.c \
  --entry-point compute --output-dir /tmp/autodeduct-acta
```

Only AcTa and CBMC are used in this mode; Saida, TriCera, ISP, WP and LLM
dependencies are unnecessary. If you built AcTa without installing it, pass
`--acta-plugin /absolute/path/to/AcTa/_build/default/src/Acta.cmxs`.
The plugin and its Frama-C executable must be built for the same version.

## Options

`--mode acta` is an alternative to the `acta` command. Common source, include,
output, entry-point, per-stage timeout and JSON options apply.
The timeout covers the whole AcTa invocation, including harness generation and CBMC.

| Option | Purpose |
| --- | --- |
| `--acta-runtime local\|docker` | Execution location; default `local` |
| `--acta-docker-image IMAGE` | Existing image; default `auto-deduct:acta` |
| `--acta-docker-platform PLATFORM` | Docker architecture; default `linux/amd64` |
| `--acta-frama-c EXECUTABLE` | AcTa frontend executable, or `AUTODEDUCT_ACTA_FRAMA_C`; default `frama-c` locally and `acta-frama-c` for the host Docker runtime |
| `--acta-plugin CMXS` | Local uninstalled plugin, or `AUTODEDUCT_ACTA_PLUGIN` |
| `--cbmc EXECUTABLE` | CBMC executable, or `AUTODEDUCT_CBMC`; default `cbmc` |
| `--cbmc-unwind N` | Positive loop bound; default `10`; unwinding assertions stay enabled |
| `--cbmc-option OPTION` | Repeat for each supported additional argument |

`--cbmc-option` arguments are passed to AcTa as a JSON argument array.
AcTa owns CBMC options and result interpretation; see its
[report interface](https://github.com/rse-verification/AcTa/tree/autodeduct-adoptation#verification-report)
for the supported arguments. For options with a value, repeat the flag:

```shell
./bin/autodeduct acta examples/acta/increment.c --entry-point compute \
  --cbmc-unwind 20 --cbmc-option=--trace \
  --cbmc-option=--object-bits --cbmc-option=12 \
  --output-dir /tmp/autodeduct-acta
```

AcTa owns harness selection, JSON output and unwinding assertions.
Options that select only some properties, disable assertions, bypass full loop
unwinding, or add source files are rejected. WP options are rejected in this mode.
`--include` directories reach both frontends. When using preprocessor macros,
pass matching definitions to both tools, for example
`--frama-c-option=-cpp-extra-args=-DTEST --cbmc-option=-DTEST`.

## Results and limits

| Artifact | Contents |
| --- | --- |
| `acta-harness.c` | Original source plus the generated harness |
| `acta-report.json` | AcTa's versioned verification status and property counts |
| `cbmc.json`, `cbmc.json.stderr.log` | Raw CBMC stdout and stderr, written by AcTa |
| `report.json` | AutoDeduct mode, stages, commands, errors, and imported `cbmc_report` summary |
| `acta_verify.*.log` | AcTa invocation stdout/stderr |
| `acta_image.*.log` | Docker image resolution, for host Docker runs |

Exit `0` requires AcTa exit zero and a valid version-1 `passed` report matching
the requested entry and loop bound, with CBMC exit zero and nonempty successful
property counts. AcTa checks the underlying CBMC evidence, entry `ensures`
assertions and unwinding assertions. AutoDeduct does not launch CBMC separately
or parse its raw output. Failure, missing/malformed reports or timeout returns
`1`. Original source files are never overwritten; known artifacts are cleared
before reruns.

This is bounded model checking under the input's preconditions and C initial
state. A passing run is evidence for that harness and model; inspect the loop
bound, generated code, assumptions and property list. AcTa's current translation
supports a limited subset of entry `requires` and `ensures`. It does not check
`assigns` clauses, turn external ACSL contracts into CBMC stubs, or materialize
ACSL ghost code as executable C. Global variables retain their C initialization;
the harness does not make all global state symbolic. Unsupported ACSL, including
named predicates, can stop harness generation. See
[AcTa issue #3](https://github.com/rse-verification/AcTa/issues/3).

AcTa remains a Frama-C plugin at the pinned revision. The optional image keeps
its Frama-C 31 installation in a separate switch and exposes it through
`acta-frama-c`; the main Frama-C 33 installation continues to serve the
deductive and LOGOS workflows.

## Integration checks

```shell
AUTODEDUCT_RUN_ACTA_DOCKER=1 AUTODEDUCT_IMAGE=auto-deduct:acta \
python3 -m unittest discover -s tests -p test_acta_integration.py -v
```

For local tool execution, set `AUTODEDUCT_RUN_ACTA_LOCAL=1` instead. The checks
cover a correct contract, a counterexample, insufficient and sufficient loop
unwinding, unsupported/missing contracts, headers, custom entry points, and
paths containing spaces. No LLM calls are involved.

CI runs these real-tool checks when the repository secret `ACTA_GITHUB_TOKEN`
contains a token with read access to AcTa. Without that secret, the public
regressions and offline AcTa tests still run; private-source integration steps
are skipped.
