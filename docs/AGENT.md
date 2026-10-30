# Agent setup and usage

[Documentation index](README.md) · [Host launcher](INSTALLATION.md#host-launcher) · [Common CLI options](USAGE.md)

Agent mode uses authenticated Codex on the host to author function contracts using
[LOGOS](https://github.com/rse-verification/logos). AutoDeduct then explicitly
runs the LOGOS Python wrapper to insert contracts and run Frama-C WP.

## Choose the runtime

| Requirement | `local` | `docker` |
| --- | --- | --- |
| Host Python 3.10+ and AutoDeduct checkout | Required | Required |
| Host Codex CLI and login | Required | Required |
| Local LOGOS checkout and skill path | Required | Unnecessary; extracted from image |
| Host libclang and Frama-C/WP/provers | Required | Supplied by verifier image |
| Docker and prepared LOGOS verifier image | Unused | Required |

`local` is the default. Docker is never started just by selecting Agent mode.
Both runtimes need the [host launcher](INSTALLATION.md#host-launcher): use
`./bin/autodeduct` from the checkout or put `bin/` on `PATH`. A separate
AutoDeduct package installation is unnecessary.

## Set up the host agent

Use the [Windows/WSL 2, Ubuntu or macOS quickstart](AGENT_DOCKER_QUICKSTART.md)
for platform setup and a complete Docker example. Windows Agent Docker commands
run in WSL 2, with Python and Codex installed inside that distribution.

Install [Codex CLI](https://learn.chatgpt.com/docs/cli) on the host and sign in:

```shell
codex login
codex --version
export PATH="$PWD/bin:$PATH"
```

Run this setup from the AutoDeduct checkout. For Docker verification with a
prepared image, proceed to [Docker usage](#run-with-docker-verification).
No separate LOGOS checkout or global skill installation is needed at runtime.

## Local verification dependencies

For local verification, clone LOGOS from its public repository:

```shell
git clone https://github.com/rse-verification/logos.git ../logos
git -C ../logos checkout cea177911b6ad5176122b4b3c415f92897c464d2
export AUTODEDUCT_AGENT_SKILL="$(cd ../logos && pwd)/skill/SKILL.md"
```

This revision is on LOGOS's `main` branch and supports the
`generate-only` task, dependency preflight, and verifier evidence interface.
No global skill registration is necessary. Keep the skill and
runner files outside the selected proof output directory. `--agent-skill PATH`
can replace the environment variable. These settings apply only to `local`.

Follow [LOGOS setup](https://github.com/rse-verification/logos/blob/main/docs/SETUP.md)
for the libclang shared library; the `clang` executable alone is insufficient.
Install Frama-C/WP and configure the provers on the host. Native Windows Python
annotation is covered by LOGOS tests; full native Windows Frama-C verification
is unvalidated. Use WSL for a Linux verification toolchain.

Run with local verification:

```shell
autodeduct agent --agent-runtime local --timeout 1200 \
  --output-dir /tmp/agent-local-proof --wp-rte path/to/program.c
```

## Build the verifier image

Run these commands **on the host, from the AutoDeduct checkout** after starting
Docker. The standard image includes LOGOS, Saida, ISP, TriCera, AcTa and CBMC.
Prepare the [GitHub build credentials](INSTALLATION.md#github-access-for-image-builds)
and use the shared [Frama-C 33 setup](ACTA.md#frama-c-33-compatibility):

```shell
docker build --secret id=github_token,env=GH_TOKEN \
  -t auto-deduct:latest -f Dockerfiles/AutoDeductDockerfile .
```

The Dockerfile fetches its pinned LOGOS revision inside the build, just as it
fetches the other components. **Do not clone LOGOS for this Docker setup.**
No separate LOGOS layer or named build context is needed. If you already have
this standard image, skip the build and proceed to the command below.

On Apple Silicon, add `--platform linux/amd64`; the runtime defaults to that
platform. See [installation](INSTALLATION.md#standard-docker-image) for
component versions. The build fetches LOGOS from its public repository.
Only its `skill/` directory and resolved revision record are retained; Git
history and credentials are absent from the image.

## Run with Docker verification

Run on the host with the host launcher, authenticated Codex, Docker and the
prepared image available locally:

```shell
autodeduct agent --agent-runtime docker --timeout 1200 \
  --agent-docker-image auto-deduct:latest \
  --output-dir /tmp/agent-docker-proof --wp-rte path/to/program.c
```

The verifier image contains Python, libclang, LOGOS, Frama-C/WP and provers.
`--agent-docker-image` defaults to the standard `auto-deduct:latest` image.
AutoDeduct resolves its tag to an immutable image ID and extracts
`/opt/logos/skill/SKILL.md` into a temporary host folder outside the agent's
output workspace. Codex reads that copy; the wrapper runs from the same image
ID. No local LOGOS checkout, `--agent-skill` flag, or host wrapper installation is
required. Docker mode always uses the image's skill, even if
`AUTODEDUCT_AGENT_SKILL` or `--agent-skill` is set.

It contains no Codex installation or model login. Source/header directories are
mounted read-only at the same absolute paths, and the output folder is writable
with the host UID/GID. The container has a read-only root filesystem, temporary
`/tmp`, no added capabilities and no network access. Host libclang and Frama-C
are unnecessary. AutoDeduct runs extraction and dependency checks before Codex,
and annotation/verification after generation. Codex does not launch Docker.

The temporary skill folder is removed when the workflow ends. The run keeps
`agent-skill.md` for review, and `agent-task.json` records its hash and the image ID.
The temporary `skill` path recorded in that task is no longer present afterwards.

Use `--agent-docker-image IMAGE` for a compatible alternate image and
`--agent-docker-platform PLATFORM` for its platform. Docker Desktop must permit
sharing the selected directories. Docker mode uses POSIX paths; on Windows use
WSL. Mount paths containing commas or newlines are unsupported. Extra resources
referenced through raw Frama-C options must be under source/`--include` roots.

`--timeout` limits each external stage separately. `--wp-option=-wp-timeout=30`
sets each prover's timeout. Larger inputs may need more than the default
300-second stage limit. Incomplete or zero-goal proofs fail; extending the time
limit does not make a failed proof successful by itself.

### Choose a custom image name

The launcher uses an image already available in the local Docker daemon. It
does not build or pull images automatically. Build or load the image first,
then pass the same name and tag with `--agent-docker-image`:

```shell
# From the AutoDeduct checkout; on Apple Silicon add --platform linux/amd64.
docker build --secret id=github_token,env=GH_TOKEN -t my-autodeduct:agent \
  -f Dockerfiles/AutoDeductDockerfile .

autodeduct agent --agent-runtime docker \
  --agent-docker-image my-autodeduct:agent \
  --timeout 1200 --wp-rte \
  --output-dir /tmp/agent-docker-proof path/to/program.c
```

Without this option, the launcher selects `auto-deduct:latest`. An image ID is
also accepted. The selected image must contain LOGOS and its verifier toolchain.

## Why Codex stays on the host

Running Codex inside Docker is unsupported and AutoDeduct rejects container
Agent launches. Earlier experiments failed during namespace/seccomp sandbox
initialization; container login also needs separate setup. The host launcher
uses the existing Codex login and coordinates generation and verification
through files. See the official [sandbox guidance](https://learn.chatgpt.com/docs/agent-approvals-security).

The traditional [deductive workflow](DEDUCTIVE.md) can still run entirely inside
Docker. That arrangement does not start a contract-generation agent.

## Contract and report handoff

1. AutoDeduct selects the local skill, or resolves the Docker image and extracts
   its skill. It checks verification dependencies before calling the model.
2. It writes `agent-task.json` with `workflow: "generate-only"`, source and output
   paths, and requested verification arguments.
3. Codex reads the skill/source and writes `agent-contracts.json` with structured
   ACSL contracts and a matching source hash, then exits.
4. AutoDeduct validates the contract bundle, invokes the LOGOS wrapper, and
   retains annotated `inferred.c` and text/PDF reports.
5. The wrapper produces `agent-verification.json` from the actual Frama-C process.
   AutoDeduct checks the annotated-source hash, unchanged input/specifications,
   exact verification arguments, exit code and complete nonzero WP summary,
   then writes its own `report.json`.

The JSON verifier evidence drives AutoDeduct's decision. Text/PDF reports are
for human review. The model's final prose is not proof evidence.

| Artifact | Owner and purpose |
| --- | --- |
| `agent-task.json` | AutoDeduct generation request, skill hash and Docker image ID |
| `agent-skill.md` | Docker skill snapshot; the temporary host copy is removed |
| `agent-contracts.json` | Host agent's contracts with source hash |
| `inferred.c` | LOGOS annotated source |
| `agent-verification.json` | LOGOS process evidence |
| `inferred.wp-report.txt` / `.pdf` | LOGOS human-readable reports |
| Stage logs and `agent-final.txt` | Image/skill setup, dependency, generation and verification diagnostics |
| `report.json` | AutoDeduct's final acceptance decision |

Evidence schema version 1 contains the command, process `returncode`,
`source_sha256`, `stdout` and `stderr`. LOGOS adds `verified` and
`verification_error`. Frama-C may return zero for incomplete proofs; success
requires a final nonzero proved/total count with every goal proved. The wrapper
is trusted software; these reports are not cryptographically certified proofs.

## Codex configuration

The default is `codex exec`. `--agent-runner COMMAND` or `AUTODEDUCT_AGENT_RUNNER`
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
to the supplied contracts and assumptions, not proof that the Agent captured all
intended requirements. Agent feature coverage and generation reliability remain
under investigation; see [Agent limitations](LIMITATIONS.md#agent-mode-coverage-under-investigation).

## Offline integration check

With the verifier image prepared (no host LOGOS checkout is needed):

```shell
AUTODEDUCT_RUN_LOGOS_DOCKER=1 \
python3 -m unittest discover -s tests -p test_logos_integration.py -v
```

This runs the host launcher with a fixed test contract writer and real LOGOS/WP,
including an intentionally incomplete specification. It does not call a model.
For the separate local integration check, set `AUTODEDUCT_LOGOS_ROOT` to a
compatible checkout and provide Frama-C on the host `PATH`.
