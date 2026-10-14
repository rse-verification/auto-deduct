# LLM setup and usage

[Documentation index](README.md) · [Host launcher](INSTALLATION.md#host-launcher) · [Common CLI options](USAGE.md)

LLM mode uses authenticated Codex on the host to author function contracts using
[LOGOS](https://github.com/rse-verification/logos). AutoDeduct then explicitly
runs the LOGOS Python wrapper to insert contracts and run Frama-C WP.

## Choose the runtime

| Requirement | `local` | `docker` |
| --- | --- | --- |
| Host Python 3.10+ and AutoDeduct checkout | Required | Required |
| Host Codex CLI and login | Required | Required |
| Local LOGOS skill checkout | Required | Required |
| Host libclang and Frama-C/WP/provers | Required | Supplied by verifier image |
| Docker and prepared LOGOS verifier image | Unused | Required |

`local` is the default. Docker is never started just by selecting LLM mode.
Both runtimes need the [host launcher](INSTALLATION.md#host-launcher): use
`./bin/autodeduct` from the checkout or put `bin/` on `PATH`. A separate
AutoDeduct package installation is unnecessary.

## Set up the host agent and LOGOS

Install [Codex CLI](https://learn.chatgpt.com/docs/cli) on the host and sign in:

```shell
codex login
codex --version
```

From the AutoDeduct checkout, clone LOGOS using your normal GitHub authentication:

```shell
git clone https://github.com/rse-verification/logos.git ../logos
git -C ../logos checkout 403334b11109d3d5eca9356b1529610cd9e57616
export AUTODEDUCT_LLM_SKILL="$(cd ../logos && pwd)/skill/SKILL.md"
export PATH="$PWD/bin:$PATH"
```

This revision is on LOGOS's `llm-host-runtime` branch and supports the
`generate-only` task, dependency preflight, and verifier evidence interface. Repository access is required while LOGOS
is private. No global skill registration is necessary. Keep the skill and
runner files outside the selected proof output directory.

## Local verification dependencies

Follow [LOGOS setup](https://github.com/rse-verification/logos/blob/llm-host-runtime/docs/SETUP.md)
for the libclang shared library; the `clang` executable alone is insufficient.
Install Frama-C/WP and configure the provers on the host. Native Windows Python
annotation is covered by LOGOS tests; full native Windows Frama-C verification
is unvalidated. Use WSL for a Linux verification toolchain.

Run with local verification:

```shell
autodeduct llm --llm-runtime local --timeout 1200 \
  --output-dir /tmp/llm-local-proof --wp-rte path/to/program.c
```

## Build the verifier image

Install/start Docker and [build the standard image](INSTALLATION.md#traditional-docker-toolchain),
then build the LOGOS layer from the same checkout as the host skill:

```shell
docker build \
  --build-context logos=../logos \
  --build-arg LOGOS_REV="$(git -C ../logos rev-parse HEAD)" \
  -t auto-deduct:logos -f Dockerfiles/LogosDockerfile .
```

BuildKit/named build contexts are required. On Apple Silicon, add
`--platform linux/amd64` to both image builds. The runtime defaults to that
platform. `LOGOS_REV` records the chosen checkout as an image label; it does
not select it. Use `--build-arg AUTODEDUCT_IMAGE=IMAGE` to reuse another compatible base.
Only LOGOS's `skill/` directory, including its GPL-2.0-only license, is copied.
No source case studies, Git history or credentials are embedded.

## Run with Docker verification

Run on the host after the setup above:

```shell
autodeduct llm --llm-runtime docker --timeout 1200 \
  --output-dir /tmp/llm-docker-proof --wp-rte path/to/program.c
```

The verifier image contains Python, libclang, LOGOS, Frama-C/WP and provers.
It contains no Codex installation or model login. Source/header directories are
mounted read-only at the same absolute paths, and the output folder is writable
with the host UID/GID. The container has a read-only root filesystem, temporary
`/tmp`, no added capabilities and no network access. Host libclang and Frama-C
are unnecessary. Codex does not launch Docker; AutoDeduct does that afterwards.

Use `--llm-docker-image IMAGE` for a compatible alternate image and
`--llm-docker-platform PLATFORM` for its platform. Docker Desktop must permit
sharing the selected directories. Docker mode uses POSIX paths; on Windows use
WSL. Mount paths containing commas or newlines are unsupported. Extra resources
referenced through raw Frama-C options must be under source/`--include` roots.

`--timeout` limits each external stage separately. `--wp-option=-wp-timeout=30`
sets each prover's timeout. Larger inputs may need more than the default
300-second stage limit. Incomplete or zero-goal proofs fail; extending the time
limit does not make a failed proof successful by itself.

## Why Codex stays on the host

Running Codex inside Docker is unsupported and AutoDeduct rejects container
LLM launches. Earlier experiments failed during namespace/seccomp sandbox
initialization; container login also needs separate setup. The host launcher
uses the existing Codex login and coordinates generation and verification
through files. See the official [sandbox guidance](https://learn.chatgpt.com/docs/agent-approvals-security).

The traditional [deductive workflow](DEDUCTIVE.md) can still run entirely inside
Docker. That arrangement does not start an LLM agent.

## Contract and report handoff

1. AutoDeduct checks verification dependencies for the selected runtime.
2. It writes `llm-task.json` with `workflow: "generate-only"`, source and output
   paths, and requested verification arguments.
3. Codex reads the skill/source and writes `llm-contracts.json` with structured
   ACSL contracts and a matching source hash, then exits.
4. AutoDeduct validates the contract bundle, invokes the LOGOS wrapper, and
   retains annotated `inferred.c` and text/PDF reports.
5. The wrapper produces `llm-verification.json` from the actual Frama-C process.
   AutoDeduct checks the annotated-source hash, unchanged input/specifications,
   exact verification arguments, exit code and complete nonzero WP summary,
   then writes its own `report.json`.

The JSON verifier evidence drives AutoDeduct's decision. Text/PDF reports are
for human review. The model's final prose is not proof evidence.

| Artifact | Owner and purpose |
| --- | --- |
| `llm-task.json` | AutoDeduct generation request |
| `llm-contracts.json` | Host agent's contracts with source hash |
| `inferred.c` | LOGOS annotated source |
| `llm-verification.json` | LOGOS process evidence |
| `inferred.wp-report.txt` / `.pdf` | LOGOS human-readable reports |
| Stage logs and `llm-final.txt` | Dependency, generation and verification diagnostics |
| `report.json` | AutoDeduct's final acceptance decision |

Evidence schema version 1 contains the command, process `returncode`,
`source_sha256`, `stdout` and `stderr`. LOGOS adds `verified` and
`verification_error`. Frama-C may return zero for incomplete proofs; success
requires a final nonzero proved/total count with every goal proved. The wrapper
is trusted software; these reports are not cryptographically certified proofs.

## Codex configuration

The default is `codex exec`. `--llm-runner COMMAND` or `AUTODEDUCT_LLM_RUNNER`
can select a Codex profile. The command receives Codex-specific arguments;
other agents and direct APIs need an adapter. Commands execute without a shell;
script paths must be absolute. Do not put credentials in the command because
it appears in reports. Input and specifications are sent to the configured
model; use an account suitable for those files.

Codex uses a workspace-write sandbox rooted at the output folder.
`--approve-for-me` uses its own automatic approval policy. The agent only writes
contract JSON; the launcher owns annotation, Docker calls and proof evidence.

## Troubleshooting and boundaries

| Symptom | Check |
| --- | --- |
| `autodeduct: command not found` | Use `./bin/autodeduct` or add the checkout's `bin/` to `PATH` |
| Missing libclang or Frama-C | Complete local dependencies or rebuild the verifier image |
| Docker unavailable, image missing or mounts denied | Start Docker, build/select the image and enable folder sharing |
| Model unavailable or login failure | Check host Codex configuration; generation stops before verification |
| Contract/source hash mismatch | Regenerate contracts for this exact input |
| Unproved WP goals | Inspect the LOGOS report; review requirements, frames, initialization, invariants and assumptions |

LOGOS requires existing ACSL in the input and explicit contracts for
undocumented functions. It does not infer loop invariants through ISP/Eva,
and this mode provides no ISP helper-coverage guarantee. Project-specific
include/macro options are forwarded to verification, not to libclang's annotation
parser. Native end-to-end host verification remains unqualified in this branch;
Docker verification has been checked with real WP. Proof success is relative
to the supplied contracts and assumptions, not proof that the LLM captured all
intended requirements. See [limitations](LIMITATIONS.md).

## Offline integration check

With the compatible LOGOS checkout and verifier image configured:

```shell
AUTODEDUCT_LOGOS_ROOT="$(cd ../logos && pwd)" \
AUTODEDUCT_RUN_LOGOS_DOCKER=1 \
python3 -m unittest discover -s tests -p test_logos_integration.py -v
```

This runs the host launcher with a fixed test contract writer and real LOGOS/WP,
including an intentionally incomplete specification. It does not call a model.
