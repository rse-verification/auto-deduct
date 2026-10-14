# Installation

[Documentation index](README.md) · [Deductive usage](DEDUCTIVE.md) · [LLM setup and usage](LLM.md)

Choose a setup before running a command:

| Workflow | Setup |
| --- | --- |
| Deductive with Docker | Build the [standard image](#standard-docker-image); host Python/Codex are unnecessary |
| Deductive locally | Install the [native toolchain](#native-installation) and host launcher |
| LLM locally | Install the [host launcher](#host-launcher), then follow [LLM local setup](LLM.md#local-verification-dependencies) |
| LLM with Docker verification | Install the host launcher, then follow [LLM Docker setup](LLM.md#build-the-verifier-image) |

## Host launcher

Both LLM runtimes need AutoDeduct on the host, plus Python 3.10+.
A separate package installation is unnecessary. Clone the branch and use its
included executable:

```shell
git clone --branch v2.0.0-rc.1 https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
./bin/autodeduct --version
```

From this directory, run `./bin/autodeduct ...` directly. For the short command:

```shell
export PATH="$PWD/bin:$PATH"
autodeduct --version
```

The export applies to the current terminal. For future sessions, add the absolute
checkout `bin/` path to your shell's `PATH` setup. Installing only the Docker image
is insufficient for LLM mode. The traditional Docker command runs the CLI inside
the image and does not need a host CLI installation.

LLM Docker mode extracts the LOGOS skill from its verifier image. A separate
local LOGOS checkout is required only for local verification. The standard
Docker build fetches LOGOS itself, alongside the other components.
See [LLM setup](LLM.md).

<a id="traditional-docker-toolchain"></a>

## Standard Docker image

Clone the repository and build from its root. The root is required because
the Dockerfile copies the CLI from `bin/`. The standard image includes
Saida, ISP, TriCera, Frama-C/WP, LOGOS and libclang. Choose the workflow when
running AutoDeduct; a second image build or host LOGOS checkout is unnecessary.

```shell
git clone --branch v2.0.0-rc.1 https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
docker build \
  -t auto-deduct:v2-rc \
  -t auto-deduct:latest \
  -f Dockerfiles/AutoDeductDockerfile .
```

Verify the image:

```shell
docker run --rm auto-deduct:latest autodeduct --version
docker run --rm auto-deduct:latest autodeduct --help
docker run --rm auto-deduct:latest python3 /opt/logos/skill/scripts/generate_acsl.py --check-dependencies
```

The build fetches pinned component revisions directly from their public
repositories. No separate LOGOS checkout or GitHub credentials are needed.

You may choose another image name with `docker build -t NAME:TAG`. For LLM
Docker runs, select it with `--llm-docker-image NAME:TAG`; for deductive Docker
runs, use it as the image argument to `docker run`. LLM mode defaults to
`auto-deduct:latest` and never builds or pulls the selected image automatically.
See the [custom image example](LLM.md#choose-a-custom-image-name).

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
LOGOS is pinned to commit `cea177911b6ad5176122b4b3c415f92897c464d2`
on its `main` branch.

The Dockerfile accepts `SAIDA_REPO`, `TRICERA_REPO`, `ISP_REPO`, and `LOGOS_REPO`,
together with `OCAML_VER`, `SAIDA_VER`, `TRICERA_VER`, `ISP_VER`, and `LOGOS_VER`.
A component version may be a branch, tag, or commit reachable from the selected
repository.

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
inside the image; LOGOS records its commit in `/opt/logos/REVISION`. Only LOGOS's
`skill/` directory and that revision record are retained, including its license;
its temporary checkout and Git history are removed. Prefer immutable tags or
commits for release images. Add `--no-cache` when deliberately retesting a
moving branch that Docker may have cached.

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

## LOGOS for LLM mode

The complete guide has moved to [LLM setup and usage](LLM.md). It covers the
compatible LOGOS revision, host Codex login, local dependencies, verifier image
build and runtime selection. Codex inside Docker is unsupported.
