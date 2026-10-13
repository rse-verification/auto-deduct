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
Compatible integration revision: `851cd3a71dc265ebaeeffffa69c8f215fb2f47ff`.
This revision adds the evidence/options interface required by AutoDeduct's
`llm-skill-mode` branch and rejects incomplete WP proofs. The earlier
libclang-only fix does not implement that interface.

Clone LOGOS alongside AutoDeduct using your normal GitHub authentication
(repository access is required while LOGOS is private):

```shell
# From the AutoDeduct repository root:
git clone https://github.com/rse-verification/logos.git ../logos
git -C ../logos checkout 851cd3a71dc265ebaeeffffa69c8f215fb2f47ff
```

For native use, follow LOGOS's prerequisites, install/authenticate
[Codex CLI](https://learn.chatgpt.com/docs/cli), and set
`AUTODEDUCT_LLM_SKILL` to the absolute path of `../logos/skill/SKILL.md`.
No global skill registration is required. The whole skill directory and its
scripts must be readable by the runner.

### Build the LOGOS Docker image

Build the standard `auto-deduct:latest` image first, as above. Then:

```shell
docker build \
  --build-context logos=../logos \
  --build-arg LOGOS_REV="$(git -C ../logos rev-parse HEAD)" \
  -t auto-deduct:logos -f Dockerfiles/LogosDockerfile .
```

Use Docker with BuildKit/named build context support. The named context is
required and must point to the LOGOS repository root. Only `skill/` is copied
to `/opt/logos/skill`, including its GPL-2.0-only `LICENSE`; no Git credentials are passed to the build. Check out
the chosen revision before building; `LOGOS_REV` records it as an image label
and does not select the checkout for you.

This layer installs libclang and Codex CLI `0.162.1` and sets
`AUTODEDUCT_LLM_SKILL=/opt/logos/skill/SKILL.md`. It also copies this checkout's
AutoDeduct CLI. Override `AUTODEDUCT_IMAGE` to reuse a compatible toolchain
image, or `CODEX_VERSION` to deliberately test another CLI version.
On Apple Silicon, add `--platform linux/amd64` to all Docker build/run commands.

### Authenticate and run

Check that the host permits Codex's Linux sandbox before starting a model run:

```shell
docker run --rm auto-deduct:logos codex sandbox linux -- /bin/true
```

This makes no model call. If it fails with a `bwrap` namespace-permission error,
the Docker host's namespace/security policy is incompatible with the sandbox.
Resolve that runtime configuration before running LLM mode; a successful image
build or fixed-contract test does not establish sandbox compatibility.

Keep Codex login state in a runtime volume, outside the image:

```shell
docker volume create logos-codex
docker run --rm -it -v logos-codex:/home/dev/.codex \
  auto-deduct:logos codex login --device-auth
```

Device login must be enabled for the account/workspace. Other supported login
methods are described in the [official authentication documentation](https://learn.chatgpt.com/docs/auth).
No model credentials are stored in the Dockerfile.

```shell
docker run --rm \
  -v logos-codex:/home/dev/.codex \
  -v "$PWD":/work:ro -w /work \
  -v "$PWD/../logos-proof":/output \
  auto-deduct:logos autodeduct --mode llm --timeout 1200 \
  --output-dir /output --wp-rte tests/fixtures/v1_smoke.c
```

Create `../logos-proof` first and make it writable by the container's `dev`
user (UID 2000 by default). Use a separate output directory, outside the
mounted source tree. The Codex runner retains its workspace-write sandbox;
the container host must support it. Authentication, model access, and sandbox
permissions are runtime prerequisites; failures are reported rather than
bypassed. The fixed-contract integration test below does not test live model
access or the Codex sandbox.

### Check the LOGOS/WP interface without a model call

```shell
docker run --rm \
  -v "$PWD":/work:ro -w /work \
  -e AUTODEDUCT_LOGOS_ROOT=/opt/logos \
  auto-deduct:logos python3 -m unittest discover -s tests \
  -p test_logos_integration.py -v
```

This uses a test-only fixed contract runner with the real LOGOS wrapper and
Frama-C WP. It checks the requested proof options, evidence hash, source
preservation, successful proof acceptance, and rejection of an incomplete
proof despite Frama-C returning zero. It does not call an LLM or run the
Saida/ISP inference stages.
