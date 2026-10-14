# Installation

Docker is the recommended way to obtain compatible versions of Frama-C,
Saida, TriCera, ISP, and the WP provers. A native installation is also
supported when the matching tools are already available on the host.

## Docker

Clone the repository and build from its root. The root is required because
the Dockerfile copies the CLI from `bin/`.

```shell
git clone --branch llm-skill-mode https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
docker build \
  -t auto-deduct:1.0.0 \
  -t auto-deduct:latest \
  -f Dockerfiles/AutoDeductDockerfile .
```

Verify the image:

```shell
docker run --rm auto-deduct:latest autodeduct --version
docker run --rm auto-deduct:latest autodeduct --help
```

## Apple Silicon

The current TriCera stack uses the `linux/amd64` architecture. Add the
platform to both build and run commands on an Apple Silicon Mac:

```shell
docker build --platform linux/amd64 \
  -t auto-deduct:latest \
  -f Dockerfiles/AutoDeductDockerfile .

docker run --rm --platform linux/amd64 \
  auto-deduct:latest autodeduct --version
```

## Component Versions

The default image uses OCaml 5.4.0, Frama-C 33.0, ISP `v0.4.0`, Saida
`v0.6.0`, and TriCera `v0.5`. All three analysis components are pinned to
releases. OCaml is installed in the image's default opam switch rather than
inherited from the Ubuntu package version.

The Dockerfile accepts `SAIDA_REPO`, `TRICERA_REPO`, and `ISP_REPO`, together
with `OCAML_VER`, `SAIDA_VER`, `TRICERA_VER`, and `ISP_VER`. A component version
may be a branch, tag, or commit reachable from the selected repository.

```shell
docker build \
  --build-arg OCAML_VER=5.4.0 \
  --build-arg SAIDA_VER=<branch-tag-or-commit> \
  --build-arg TRICERA_VER=<branch-tag-or-commit> \
  --build-arg ISP_VER=<branch-tag-or-commit> \
  -t auto-deduct:component-test \
  -f Dockerfiles/AutoDeductDockerfile .
```

For a fix hosted in a fork, set both its repository and ref:

```shell
docker build \
  --build-arg TRICERA_REPO=https://github.com/<user>/tricera.git \
  --build-arg TRICERA_VER=<branch-or-commit> \
  -t auto-deduct:component-test \
  -f Dockerfiles/AutoDeductDockerfile .
```

Each resolved component commit is stored in `/home/dev/repos/<component>/REVISION`
inside the image. Prefer immutable tags or commits for release images. Add
`--no-cache` when deliberately retesting a moving branch that Docker may have
cached.

## Corporate Proxy Builds

Only networks requiring an HTTP proxy need these optional arguments:

```shell
docker build \
  --build-arg PROXY_HOST=<proxy-host> \
  --build-arg PROXY_PORT=<proxy-port> \
  -t auto-deduct:latest \
  -f Dockerfiles/AutoDeductDockerfile .
```

Proxy configuration is not required on a normal direct Internet connection.

## Native Installation

Running without Docker requires:

- Python 3.10 or newer
- OCaml 5.4 or newer in the active opam switch
- Frama-C 33 with Saida and ISP installed
- the TriCera `tri` executable
- SMT provers configured for WP

The Python CLI has no additional package dependencies. From the repository
root, expose it on `PATH` and check the tools:

```shell
chmod +x bin/autodeduct
export PATH="$PWD/bin:$PATH"
python3 --version
command -v frama-c
command -v tri
frama-c -plugins | grep -Ei "saida|isp"
autodeduct --version
```

Docker remains the reproducible option when compatible host components are
not already installed.

## LOGOS for LLM Mode

Repository: [rse-verification/logos](https://github.com/rse-verification/logos).
Compatible integration revision: `2bd60124a499373cfc7a90fa3a226225758db993`.
This revision supports the generation-only task used by the host launcher,
plus the evidence/options interface and rejection of incomplete WP proofs.
It is available on LOGOS branch `llm-host-runtime`.

Clone LOGOS alongside AutoDeduct using your normal GitHub authentication
(repository access is required while LOGOS is private):

```shell
# From the AutoDeduct repository root:
git clone https://github.com/rse-verification/logos.git ../logos
git -C ../logos checkout 2bd60124a499373cfc7a90fa3a226225758db993
```

### Host Setup (Both LLM Runtimes)

Install Python 3.10+ and an authenticated
[Codex CLI](https://learn.chatgpt.com/docs/cli) on your computer. Run `codex login`
on the host, then check `codex --version`. Clone the compatible LOGOS revision
above and set its skill path:

```shell
export AUTODEDUCT_LLM_SKILL="$(cd ../logos && pwd)/skill/SKILL.md"
export PATH="$PWD/bin:$PATH"
```

Global skill registration is unnecessary. The host agent reads the local skill
and source and produces contract JSON. AutoDeduct then runs the LOGOS wrapper
and checks its proof evidence. The current adapter requires Codex; other agents
or direct model APIs are not interchangeable through `--llm-runner`.

### Without Docker

Follow LOGOS's libclang prerequisites, install Frama-C/WP and configure its
provers locally. Then:

```shell
autodeduct llm --llm-runtime local --timeout 1200 \
  --output-dir /tmp/logos-proof path/to/program.c
```

Local execution is the default and needs no Docker. Full native verification
on Windows is unvalidated; use WSL for the Linux verification toolchain.

### With Docker Verification

Install/start Docker and build the standard `auto-deduct:latest` image first,
as above. Then build the verifier image from the same LOGOS revision as the
host checkout:

```shell
docker build \
  --build-context logos=../logos \
  --build-arg LOGOS_REV="$(git -C ../logos rev-parse HEAD)" \
  -t auto-deduct:logos -f Dockerfiles/LogosDockerfile .
```

The named build context requires BuildKit support. It copies only `skill/`
(including the GPL-2.0-only license) to `/opt/logos/skill`; no Git history or
credentials are copied. `LOGOS_REV` records the selected checkout as a label,
not a command to switch revisions. This image adds libclang and the LOGOS
wrapper to the Frama-C/prover toolchain. It contains no Codex installation or
login state. Host libclang and Frama-C installations are unnecessary.
Override `AUTODEDUCT_IMAGE` at build time to reuse a compatible base image.
On Apple Silicon, add `--platform linux/amd64` to both image builds.

Run the launcher on the host:

```shell
autodeduct llm --llm-runtime docker --timeout 1200 \
  --output-dir /tmp/logos-proof --wp-rte path/to/program.c
```

Use `--llm-docker-image IMAGE` for another compatible image and
`--llm-docker-platform PLATFORM` for its platform (default `linux/amd64`).
Source/header directories from the source path and `--include` are mounted
read-only at the same absolute paths; only the separate output folder is
writable. The container uses your host UID/GID, has a read-only root filesystem,
a temporary `/tmp`, no added capabilities and no network access. It mounts
neither your Codex login directory nor Docker's socket. Commas/newlines in mount
paths are unsupported. Docker Desktop must allow sharing the selected folders.
Linux/macOS and Windows through WSL are supported host environments for this
runtime. Additional filesystem resources referenced through raw Frama-C options
must already be under the mounted source/include directories.

### Unsupported: Codex Inside Docker

Launch `autodeduct llm` on the host. AutoDeduct rejects container LLM launches
before clearing outputs. The traditional `autodeduct deductive` workflow still
runs entirely in Docker. Our previous all-in-one LLM experiments encountered
namespace and seccomp initialization failures. Keeping the agent on the host
also lets it use its existing login. No custom Docker security profile or
container Codex login is part of the supported setup.

### Check the LOGOS/WP interface without a model call

```shell
docker run --rm \
  -v "$PWD":/work:ro -w /work \
  -e AUTODEDUCT_LOGOS_ROOT=/opt/logos \
  auto-deduct:logos python3 -m unittest discover -s tests \
  -p test_logos_integration.py -v
```

This offline test bypasses the host-only guard with a test-only fixed contract
runner and uses the real LOGOS wrapper and
Frama-C WP. It checks the requested proof options, evidence hash, source
preservation, successful proof acceptance, and rejection of an incomplete
proof despite Frama-C returning zero. It does not call an LLM or run the
Saida/ISP inference stages.
