# Installation

Docker is the recommended way to obtain compatible versions of Frama-C,
Saida, TriCera, ISP, and the WP provers. A native installation is also
supported when the matching tools are already available on the host.

## Docker

Clone the repository and build from its root. The root is required because
the Dockerfile copies the CLI from `bin/`.

```shell
git clone https://github.com/rse-verification/auto-deduct.git
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
