# LLM Docker quickstart

[Project overview](../README.md) · [LLM setup and usage](LLM.md) · [Installation](INSTALLATION.md)

This workflow uses host Python 3.10+, Git, authenticated
[Codex CLI](https://learn.chatgpt.com/docs/cli), and a running Docker installation.
The standard image supplies LOGOS, libclang, Frama-C and provers. Choose your
platform setup, then use the shared build/run commands below. The launcher
is included in the checkout; a separate AutoDeduct package installation or
local LOGOS clone is unnecessary for this Docker workflow. Build or load the
image first; the launcher does not build or pull it automatically.

## Windows (WSL 2)

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

## Ubuntu

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

## macOS

Use Terminal with Bash or Zsh, Codex CLI and Docker Desktop running. If Git or
Python is missing, install them with Homebrew:

```bash
brew install git python
```

The shared `linux/amd64` build works for Intel and Apple Silicon Macs; the
current TriCera toolchain requires that architecture. Docker Desktop must allow
sharing the checkout and output directories.

## Build and run (Ubuntu, macOS, or Ubuntu inside WSL 2)

Run these Bash/Zsh commands on the host. In Windows, the host terminal here is
the Ubuntu WSL terminal. The PATH export applies to the current session.

```bash
# Check prerequisites: Python must be 3.10 or newer.
python3 --version
codex --version
codex login status
# If needed: codex login
docker info

git clone --branch acta-integration \
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

## Open the PDF report

| Platform | Command after verification |
| --- | --- |
| Ubuntu desktop | `xdg-open /tmp/autodeduct-stee-llm/inferred.wp-report.pdf` |
| macOS | `open /tmp/autodeduct-stee-llm/inferred.wp-report.pdf` |
| Windows/WSL 2 | `explorer.exe "$(wslpath -w /tmp/autodeduct-stee-llm)"` then open the PDF in that folder |

On Ubuntu, install `xdg-utils` if `xdg-open` is missing. On a headless server,
read the text report or copy the PDF to a computer with a PDF viewer.
This quickstart targets the current AMD64 toolchain; ARM Linux hosts need
working AMD64 emulation. See [LLM usage](LLM.md) for local verification,
custom images and further options.
