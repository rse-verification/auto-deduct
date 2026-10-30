# Installation

[Documentation index](README.md) · [Deductive usage](DEDUCTIVE.md) · [Agent setup and usage](AGENT.md)

Choose a setup before running a command:

| Workflow | Setup |
| --- | --- |
| Deductive with Docker | Build the [standard image](#standard-docker-image); host Python/Codex are unnecessary |
| Deductive locally | Install the [native toolchain](#native-installation) and host launcher |
| Agent locally | Install the [host launcher](#host-launcher), then follow [Agent local setup](AGENT.md#local-verification-dependencies) |
| Agent with Docker verification | Install the host launcher, then follow [Agent Docker setup](AGENT.md#build-the-verifier-image) |
| AcTa/CBMC locally or with Docker | Follow [AcTa setup](ACTA.md); its optional image target supplies both tools for Docker execution |

## Host launcher

For Windows/WSL 2, Ubuntu and macOS setup and a complete Agent Docker example,
see the [operating-system quickstart](AGENT_DOCKER_QUICKSTART.md).
Run the launcher in WSL 2 on Windows; the commands below use Bash/Zsh syntax.

Both Agent runtimes need AutoDeduct on the host, plus Python 3.10+.
A separate package installation is unnecessary. Clone the repository and use its
included executable:

```shell
git clone https://github.com/rse-verification/auto-deduct.git
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
is insufficient for Agent mode. The traditional Docker command runs the CLI inside
the image and does not need a host CLI installation.

Agent Docker mode extracts the LOGOS skill from its verifier image. A separate
local LOGOS checkout is required only for local verification. The standard
Docker build fetches LOGOS itself, alongside the other components.
See [Agent setup](AGENT.md).

<a id="traditional-docker-toolchain"></a>

## GitHub access for image builds

The standard image includes AcTa and CBMC alongside the other tools. AcTa is
currently private, so building any standard image requires a GitHub token with
read access to that repository. Set `GH_TOKEN` before the build; with an
already authenticated GitHub CLI, one option is:

```shell
export GH_TOKEN="$(gh auth token)"
```

The commands below pass it through a temporary BuildKit secret. It is not stored
in build arguments, Git URLs or the image environment. For an accessible fork,
set `ACTA_REPO` and `ACTA_VER` accordingly.

## Standard Docker image

Clone the repository and build from its root. The root is required because
the Dockerfile copies the CLI from `bin/`. The standard image includes
Saida, ISP, TriCera, Frama-C 33/WP, LOGOS, libclang, AcTa and CBMC.
Choose the workflow when running AutoDeduct; a second image build or host LOGOS checkout is unnecessary.

```shell
git clone https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
docker build --secret id=github_token,env=GH_TOKEN \
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

The build fetches pinned component revisions directly from their repositories.
No separate LOGOS or AcTa checkout is needed. Supply the GitHub build secret
for private AcTa access as described above.

You may choose another image name with `docker build -t NAME:TAG`, keeping the
same build secret. For Agent
Docker runs, select it with `--agent-docker-image NAME:TAG`; for deductive Docker
runs, use it as the image argument to `docker run`. Agent mode defaults to
`auto-deduct:latest` and never builds or pulls the selected image automatically.
See the [custom image example](AGENT.md#choose-a-custom-image-name).

## Apple Silicon

The current TriCera stack uses the `linux/amd64` architecture. Add the
platform to both build and run commands on an Apple Silicon Mac:

```shell
docker build --secret id=github_token,env=GH_TOKEN --platform linux/amd64 \
  -t auto-deduct:latest \
  -f Dockerfiles/AutoDeductDockerfile .

docker run --rm --platform linux/amd64 \
  auto-deduct:latest autodeduct --version
```

## Component Versions

The default image uses OCaml 5.4.0, Frama-C 33.0, ISP `v0.4.0`, Saida
`v0.6.0`, and TriCera `v0.5`. Saida is pinned to release commit
`605a4a4ae976050ec5e1060fec621ef4d6157f68`; ISP and TriCera use release tags. OCaml is installed in the image's default opam switch rather than
inherited from the Ubuntu package version.
LOGOS is pinned to commit `cea177911b6ad5176122b4b3c415f92897c464d2`
on its `main` branch.
The standard image installs AcTa in the same Frama-C 33 opam switch.
AcTa is pinned to `46c5b15807c204736cd08588d0fb5bd02b0a0d2c`, which supports
Frama-C 33 and JSON verification reports. See [AcTa setup](ACTA.md).
CBMC 6.11.0 uses official Ubuntu 24.04 amd64/arm64 packages with pinned SHA-256
digests. The TriCera architecture constraint above still applies to the full
standard image.

The Dockerfile accepts `SAIDA_REPO`, `TRICERA_REPO`, `ISP_REPO`, and `LOGOS_REPO`,
together with `OCAML_VER`, `SAIDA_VER`, `TRICERA_VER`, `ISP_VER`, and `LOGOS_VER`.
A component version may be a branch, tag, or commit reachable from the selected
repository.
AcTa adds `ACTA_REPO` and `ACTA_VER`. CBMC adds `CBMC_VER`,
`CBMC_SHA256_AMD64` and `CBMC_SHA256_ARM64`; update the matching official package
digests when changing its version.

```shell
docker build --secret id=github_token,env=GH_TOKEN \
  --build-arg OCAML_VER=5.4.0 \
  --build-arg SAIDA_VER=<branch-tag-or-commit> \
  --build-arg TRICERA_VER=<branch-tag-or-commit> \
  --build-arg ISP_VER=<branch-tag-or-commit> \
  -t auto-deduct:component-test \
  -f Dockerfiles/AutoDeductDockerfile .
```

For a fix hosted in a fork, set both its repository and ref:

```shell
docker build --secret id=github_token,env=GH_TOKEN \
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
AcTa's resolved revision is stored in `/opt/acta/REVISION`.

## Corporate Proxy Builds

Only networks requiring an HTTP proxy need these optional arguments:

```shell
docker build --secret id=github_token,env=GH_TOKEN \
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

## LOGOS for Agent mode

The complete guide has moved to [Agent setup and usage](AGENT.md). It covers the
compatible LOGOS revision, host Codex login, local dependencies, verifier image
build and runtime selection. Codex inside Docker is unsupported.
