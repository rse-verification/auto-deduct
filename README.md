# AutoDeduct V2 “Double Ducks” — release candidate

AutoDeduct generates contracts for C programs and checks them with Frama-C WP.
It accepts one C translation unit and its headers. Generated source, logs and
reports go into a separate output directory; the original input stays unchanged.

## Choose a workflow

| Command | Contract generation | Verification |
| --- | --- | --- |
| `autodeduct deductive` | Saida/TriCera, with ISP/Eva auxiliary annotations | Frama-C WP and reachable-helper coverage checks |
| `autodeduct llm` | Host Codex using [LOGOS](https://github.com/rse-verification/logos) | LOGOS wrapper runs Frama-C WP; AutoDeduct validates its evidence |

Both workflows use deductive verification. The command names distinguish how
contracts are generated. The default is `deductive`. You can also select a workflow with
`--mode deductive` or `--mode llm`.

## Start here

1. Choose your [installation](docs/INSTALLATION.md): standard Docker image,
   native tools, or the host launcher for LLM mode. For LLM Docker setup,
   start with the [Windows/WSL, Ubuntu or macOS instructions](#llm-docker-quickstart-by-operating-system).
2. Follow the usage guide for [deductive mode](docs/DEDUCTIVE.md) or
   [LLM mode](docs/LLM.md).
3. Read [common CLI options and input rules](docs/USAGE.md) and
   [how to interpret reports](docs/PIPELINE.md).

## Where commands run

| Setup | Your computer | Docker |
| --- | --- | --- |
| Deductive with Docker | Docker client | Entire traditional pipeline |
| Deductive without Docker | AutoDeduct and its verification dependencies | Unused |
| LLM with `--llm-runtime local` | Python, AutoDeduct, Codex, LOGOS and verification dependencies | Unused |
| LLM with `--llm-runtime docker` | Python, AutoDeduct launcher and authenticated Codex; skill extracted from image | LOGOS Python wrapper, libclang, Frama-C/WP and provers |

Docker is optional. **Both LLM runtimes use the host AutoDeduct launcher and
host Codex CLI.** Running Codex inside Docker is unsupported. The current LLM
adapter requires Codex; arbitrary agents and model APIs are not supported yet.

## LLM Docker quickstart by operating system

This workflow uses host Python 3.10+, Git, authenticated
[Codex CLI](https://learn.chatgpt.com/docs/cli), and a running Docker installation.
The standard image supplies LOGOS, libclang, Frama-C and provers. Choose your
platform setup, then use the shared build/run commands below. The launcher
is included in the checkout; a separate AutoDeduct package installation or
local LOGOS clone is unnecessary for this Docker workflow. Build or load the
image first; the launcher does not build or pull it automatically.

### Windows (WSL 2)

Run this workflow inside an Ubuntu WSL 2 terminal. Native PowerShell, Command
Prompt and Git Bash are not supported launch environments for LLM Docker mode.
Python, Git and Codex must be installed inside WSL; a Windows Codex installation
alone is insufficient.

**The full LLM Docker command requires WSL 2, even when you invoke the launcher
explicitly with Python.** Docker runs the verifier in Linux, but the AutoDeduct
launcher still runs in the environment where you start Python. Native Windows
Python with `--llm-runtime docker` stops with:

```text
ERROR [input]: Docker LLM mode requires POSIX host paths; use WSL on Windows
```

Changing the output directory or adding a `python` prefix does not resolve this
error. Enter Ubuntu WSL and use its Linux Python for the full run.

If Windows asks you to select an application when running `autodeduct`, it is
trying to open the extensionless Python script as a file. Adding `bin/` to
Windows `PATH` does not make it a native executable. For version/help checks
only, use Windows Python 3.10+ explicitly from the checkout in PowerShell:

```powershell
python .\bin\autodeduct --version
python .\bin\autodeduct llm --help
```

**The two PowerShell commands above are version/help checks only.** Run contract
generation and verification inside WSL 2 using the setup below.

If WSL is missing, run this in **administrator PowerShell**, then restart if
prompted and complete Ubuntu's first-run setup:

```powershell
wsl --install -d Ubuntu
```

If Ubuntu is already installed, enter it from PowerShell with:

```powershell
wsl -d Ubuntu
```

See [Microsoft's WSL setup](https://learn.microsoft.com/en-us/windows/wsl/install).
Start Docker Desktop with Linux containers and enable Ubuntu under
**Settings > Resources > WSL Integration**; see
[Docker's WSL instructions](https://docs.docker.com/desktop/features/wsl/).
Inside the Ubuntu WSL terminal:

```bash
sudo apt update
sudo apt install -y git python3
cd ~
```

Install/sign into Codex inside WSL, then run the shared commands in that same
terminal. Keep the checkout and output in the WSL Linux filesystem.
`export PATH="$PWD/bin:$PATH"` below is a Bash command, not PowerShell syntax.
After cloning and building with the shared instructions, the full command can
also be invoked explicitly with Linux Python **inside that WSL terminal**, from
the checkout:

```bash
python3 ./bin/autodeduct llm \
  --llm-runtime docker \
  --llm-docker-image auto-deduct:latest \
  --timeout 1200 --wp-rte \
  --output-dir /tmp/autodeduct-stee-llm \
  examples/ase-2024/stee.c
```

An image already built through the same Docker Desktop engine can be reused
from WSL; check `docker image inspect auto-deduct:latest` before rebuilding it.

### Ubuntu

Use a Bash terminal with Python 3.10+ and Codex available:

```bash
sudo apt update
sudo apt install -y git python3
```

Install/start [Docker Engine](https://docs.docker.com/engine/install/ubuntu/)
or Docker Desktop. `docker info` must work as your normal user because the
launcher invokes Docker without `sudo`; follow
[Docker's user-access setup](https://docs.docker.com/engine/install/linux-postinstall/)
if required. Then use the shared commands below.

### macOS

Use Terminal with Bash or Zsh, Codex CLI and Docker Desktop running. If Git or
Python is missing, install them with Homebrew:

```bash
brew install git python
```

The shared `linux/amd64` build works for Intel and Apple Silicon Macs; the
current TriCera toolchain requires that architecture. Docker Desktop must allow
sharing the checkout and output directories.

### Build and run (Ubuntu, macOS, or Ubuntu inside WSL 2)

Run these Bash/Zsh commands on the host. In Windows, the host terminal here is
the Ubuntu WSL terminal. The PATH export applies to the current session.

```bash
# Check prerequisites: Python must be 3.10 or newer.
python3 --version
codex --version
codex login status
# If needed: codex login
docker info

git clone --branch llm-skill-mode \
  https://github.com/rse-verification/auto-deduct.git
cd auto-deduct
export PATH="$PWD/bin:$PATH"

autodeduct --version
autodeduct llm --help

docker build --platform linux/amd64 \
  -t auto-deduct:latest \
  -f Dockerfiles/AutoDeductDockerfile .

autodeduct llm \
  --llm-runtime docker \
  --llm-docker-image auto-deduct:latest \
  --timeout 1200 --wp-rte \
  --output-dir /tmp/autodeduct-stee-llm \
  examples/ase-2024/stee.c

python3 -m json.tool /tmp/autodeduct-stee-llm/report.json
cat /tmp/autodeduct-stee-llm/inferred.wp-report.txt
```

This run sends source/specifications to the configured model through Codex.
If generation fails before verification, the WP reports may be absent; inspect
`report.json` and the stage logs first.

### Open the PDF report

| Platform | Command after verification |
| --- | --- |
| Ubuntu desktop | `xdg-open /tmp/autodeduct-stee-llm/inferred.wp-report.pdf` |
| macOS | `open /tmp/autodeduct-stee-llm/inferred.wp-report.pdf` |
| Windows/WSL 2 | `explorer.exe "$(wslpath -w /tmp/autodeduct-stee-llm)"` then open the PDF in that folder |

On Ubuntu, install `xdg-utils` if `xdg-open` is missing. On a headless server,
read the text report or copy the PDF to a computer with a PDF viewer.
This quickstart targets the current AMD64 toolchain; ARM Linux hosts need
working AMD64 emulation. See [LLM usage](docs/LLM.md) for local verification,
custom images and further options.

## Reports and scope

A successful run requires complete nonzero WP goals and all mandatory stages.
Use `--wp-rte` to add runtime-error obligations. Proof results depend on the
supplied specifications and assumptions; generated contracts still need review.
See [pipeline and diagnostics](docs/PIPELINE.md) and [limitations](docs/LIMITATIONS.md).

The public steering example is in [examples/ase-2024](examples/ase-2024/README.md).
Its README records provenance and commands. Input case studies remain outside
LOGOS; AutoDeduct's public regression cases are under [tests/cases](tests/cases/README.md).

## Documentation and license

Browse the [documentation index](docs/README.md) for setup, usage, reports,
troubleshooting and component versions. Release plans are in [Roadmap.md](Roadmap.md).
AutoDeduct is provided under the GNU GPLv2; see [LICENSE](LICENSE).
