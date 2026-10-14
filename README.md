# AutoDeduct 1.1 "Double Ducks" — release candidate

AutoDeduct 1.1, proposed codename "Double Ducks", is a command-line
formal-verification pipeline for C programs.
It combines Frama-C, Saida, TriCera, ISP/Eva, and WP to infer contracts and
auxiliary annotations, then checks whether the selected input can be proved.
The default `autodeduct deductive` mode retains that pipeline. The experimental
`autodeduct llm` mode uses [LOGOS: LLM-Based Generation of Function Contracts for C](https://github.com/rse-verification/logos)
through a host Codex agent for contract generation and the LOGOS Python
wrapper for annotation and verification, without Saida/TriCera, ISP/Eva,
or the ISP reachable-helper check. AutoDeduct validates its proof report.
See [LLM mode setup](docs/USAGE.md#llm-mode).

AutoDeduct never changes the input source. Generated C files, diagnostics,
logs, and the final JSON report are written to a separate output directory.

## Choose a Mode and Execution Environment

Start either mode from your terminal:

The commands below assume the checkout's `bin/` directory is in your host's
`PATH`. You can also use `./bin/autodeduct` from the repository root; see
[host launcher setup](#make-autodeduct-available-on-the-host).

```shell
autodeduct deductive path/to/program.c
autodeduct llm --llm-skill /absolute/path/to/logos/skill/SKILL.md path/to/program.c
```

These commands select how contracts are generated. Both modes use Frama-C WP
to verify them. `deductive` names the traditional Saida/TriCera/ISP/Eva pipeline;
`llm` names generation through LOGOS and an LLM agent. The existing
`--mode deterministic` and `--mode llm` flags remain supported. Without a mode,
AutoDeduct uses the traditional pipeline. Use `./llm` or `./deductive` for input
directories with those names.

The command runs wherever you launch it. `autodeduct ...` uses your local
installation; `docker run ... autodeduct ...` executes AutoDeduct inside Docker.
Choosing LLM mode does not automatically start Docker.

| Setup | On your computer | Inside Docker | Current status |
| --- | --- | --- | --- |
| Deductive with Docker | Docker client | Entire traditional pipeline | Packaged setup |
| Deductive without Docker | AutoDeduct and all traditional verification tools | Nothing | Requires compatible native dependencies |
| LLM without Docker | Python, AutoDeduct, authenticated Codex CLI, LOGOS, libclang, Frama-C/WP and provers | Nothing | Native CLI available; complete native setup not yet validated end to end |
| LLM with Docker | Python, AutoDeduct launcher and authenticated Codex CLI | LOGOS Python wrapper, libclang, Frama-C/WP and provers | Use `--llm-runtime docker` on the host |
| LLM entirely inside Docker | — | — | Unsupported |

Docker is optional for both modes when their dependencies are installed locally.
The current LLM integration requires Codex. `--llm-runner` configures a Codex
command/profile and still receives Codex-specific arguments; it does not make
arbitrary agents or model APIs interchangeable. Other LLMs need an adapter to
produce the same LOGOS contract JSON and invoke its verification wrapper.

### Why Use a Local Launcher for LLM With Docker?

Codex runs on your computer using your local login. Running Codex inside Docker
is unsupported by AutoDeduct: our trials failed during namespace and syscall-filter
initialization, and container authentication would require separate setup.
The LOGOS verifier image contains no Codex or model credentials. See the official
[sandbox guidance](https://learn.chatgpt.com/docs/agent-approvals-security).

`autodeduct llm` is the local Python launcher. It reads the input and prepares
`llm-task.json`, runs host Codex to write contract JSON, then explicitly invokes
the LOGOS wrapper. With `--llm-runtime docker`, that wrapper runs inside Docker
and uses the shared output folder to return annotated C, WP evidence, and text/PDF
reports. AutoDeduct validates the evidence and writes `report.json`. Codex does
not need permission to access Docker; the launcher starts the verifier itself.

The host needs Python 3.10+, an authenticated Codex CLI, and a local LOGOS skill
checkout. Docker mode additionally needs Docker and the LOGOS verifier image;
libclang and Frama-C are installed in the image. Local mode needs those tools
on the host and does not use Docker. Docker mode supports Linux/macOS and Windows
through WSL. Native Windows Frama-C verification remains unvalidated.

## Pipeline

Default deterministic mode:

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
successful result still requires all mandatory stages and all WP goals to pass.
Deterministic mode also requires complete reachable-helper contract coverage. See
[Pipeline and diagnostics](docs/PIPELINE.md) for the status rules.

By default, WP checks the generated contract obligations but does not add
runtime-error obligations. Use `--wp-rte` when the verification scope must also
cover runtime errors such as invalid memory accesses and arithmetic overflow;
success then requires every added RTE goal to be proved as well.

## Quick Start With Docker

```shell
git clone --branch llm-skill-mode https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
docker build -t auto-deduct:latest -f Dockerfiles/AutoDeductDockerfile .
docker run --rm \
  -v "$PWD":/work \
  -w /work \
  auto-deduct:latest \
  autodeduct deductive --entry-point main examples/ase-2024
```

On Apple Silicon, add `--platform linux/amd64` to both Docker commands.

## LLM Mode With LOGOS

### Make AutoDeduct Available on the Host

**Both `--llm-runtime local` and `--llm-runtime docker` require the AutoDeduct
launcher on your computer.** A separate AutoDeduct package installation is
unnecessary: clone this branch and use the executable included in the checkout.
Installing only the Docker image is insufficient for LLM mode.

```shell
git clone --branch llm-skill-mode https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
./bin/autodeduct --version
```

From that directory, run `./bin/autodeduct llm ...` directly. To use the shorter
`autodeduct llm ...` command, add the checkout's `bin/` directory to your `PATH`:

```shell
export PATH="$PWD/bin:$PATH"
autodeduct --version
```

This export applies to the current terminal session. To keep it for future
sessions, add the absolute checkout `bin/` path to your shell's `PATH` setup.
Both LLM runtimes also require host Python 3.10+, an installed and authenticated
Codex CLI, and the configured local LOGOS skill checkout. Docker mode provides
libclang, Frama-C/WP and provers inside the verifier image; local mode requires
those dependencies on the host.

### Configure LOGOS and Run

LOGOS supplies the skill, contract renderer, and Frama-C WP evidence wrapper.
AutoDeduct supplies the task and validates the generated artifacts and proof
evidence. Use a LOGOS revision supporting `--verification-json` and repeated
`--frama-c-option` arguments; earlier revisions are incompatible.

`Dockerfiles/LogosDockerfile` packages the LOGOS wrapper and libclang on top of
the standard verifier image. It copies your local LOGOS checkout using a Docker
named build context. It installs no Codex and uses no model login volume.
See [installation](docs/INSTALLATION.md#logos-for-llm-mode) for the compatible
LOGOS revision, host setup and image build.

Run from the host with Docker verification:

```shell
export AUTODEDUCT_LLM_SKILL="/absolute/path/to/logos/skill/SKILL.md"
./bin/autodeduct llm --llm-runtime docker --timeout 1200 \
  --output-dir /tmp/logos-proof path/to/program.c
```

Or run without Docker, with local verification dependencies installed:

```shell
./bin/autodeduct llm --llm-runtime local --timeout 1200 \
  --output-dir /tmp/logos-proof path/to/program.c
```

`local` is the default; Docker is never started implicitly. In Docker mode,
source/header directories are mounted read-only, only the output folder is
writable, and the verifier container has no network access. Existing images
must be rebuilt for the new launcher and generation-only skill protocol.

The full skill directory must be readable; global skill registration is not
required. LOGOS currently expects existing ACSL in the input and generates
function contracts. This mode does not infer loop invariants through ISP/Eva
or provide the deterministic pipeline's reachable-helper coverage check.

## Quick Start Without Docker

This requires compatible host installations of Frama-C, Saida, TriCera, ISP,
and the WP provers.

```shell
export PATH="$PWD/bin:$PATH"
autodeduct deductive \
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
- [Release limitations](docs/LIMITATIONS.md): unsupported patterns, diagnostic
  boundaries, and recommended workarounds.
- Public regression tests under `tests/cases/`: supported cases, expected
  warnings, expected limitations, and known incomplete WP outcomes.

## Public Example

`examples/ase-2024/` contains the public steering-system example associated
with the ASE 2024 paper *An Exercise in Mind Reading: Automatic Contract
Inference for Frama-C*. The example is shipped directly in this repository and
was originally copied from the public
[auto-deduct-examples](https://github.com/rse-verification/auto-deduct-examples/tree/main/ase-2024)
repository with attribution. It contains no Scania or private case-study code.
See [the example README](examples/ase-2024/README.md) for provenance and its
dedicated command.

## License

AutoDeduct is provided under the GNU GPLv2. See [LICENSE](LICENSE).
