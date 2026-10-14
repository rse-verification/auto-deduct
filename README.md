# AutoDeduct 1.1 “Double Ducks” — release candidate

AutoDeduct generates contracts for C programs and checks them with Frama-C WP.
It accepts one C translation unit and its headers. Generated source, logs and
reports go into a separate output directory; the original input stays unchanged.

## Choose a workflow

| Command | Contract generation | Verification |
| --- | --- | --- |
| `autodeduct deductive` | Saida/TriCera, with ISP/Eva auxiliary annotations | Frama-C WP and reachable-helper coverage checks |
| `autodeduct llm` | Host Codex using [LOGOS](https://github.com/rse-verification/logos) | LOGOS wrapper runs Frama-C WP; AutoDeduct validates its evidence |

Both workflows use deductive verification. The command names distinguish how
contracts are generated. The default is `deductive`; existing
`--mode deterministic` and `--mode llm` flags remain available.

## Start here

1. Choose your [installation](docs/INSTALLATION.md): traditional Docker toolchain,
   native tools, or the host launcher for LLM mode.
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
| LLM with `--llm-runtime docker` | Python, AutoDeduct launcher, authenticated Codex and local LOGOS skill | LOGOS Python wrapper, libclang, Frama-C/WP and provers |

Docker is optional. **Both LLM runtimes use the host AutoDeduct launcher and
host Codex CLI.** Running Codex inside Docker is unsupported. The current LLM
adapter requires Codex; arbitrary agents and model APIs are not supported yet.

## Quick commands

From an AutoDeduct checkout with the selected dependencies configured:

```shell
# Locally installed traditional toolchain:
./bin/autodeduct deductive --output-dir /tmp/deductive-proof path/to/program.c

# Host Codex and local LOGOS/Frama-C:
./bin/autodeduct llm --llm-runtime local \
  --llm-skill /absolute/path/to/logos/skill/SKILL.md \
  --output-dir /tmp/llm-proof path/to/program.c

# Host Codex and LOGOS verification in the prepared Docker image:
./bin/autodeduct llm --llm-runtime docker \
  --llm-skill /absolute/path/to/logos/skill/SKILL.md \
  --output-dir /tmp/llm-proof path/to/program.c
```

A separate AutoDeduct package installation is unnecessary. Use `./bin/autodeduct`
directly or add the checkout's `bin/` directory to `PATH`; see
[host launcher setup](docs/INSTALLATION.md#host-launcher).
These examples require setup first. Docker mode does not install or build its
image automatically. For larger LLM runs, see the timeout guidance in
[LLM usage](docs/LLM.md#run-with-docker-verification).

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
