# AutoDeduct documentation

Start with setup, then choose a usage guide.

| Guide | What it covers |
| --- | --- |
| [Installation](INSTALLATION.md) | Host launcher, traditional Docker/native tools, component versions and proxy builds |
| [Deductive usage](DEDUCTIVE.md) | Traditional pipeline commands in Docker or locally; outputs and manual stages |
| [LLM Docker quickstart](LLM_DOCKER_QUICKSTART.md) | Windows/WSL 2, Ubuntu and macOS prerequisites, first run and opening reports |
| [LLM setup and usage](LLM.md) | Host Codex + LOGOS setup, local/Docker verification, JSON handoff and LLM troubleshooting |
| [AcTa and CBMC](ACTA.md) | Harness generation from existing contracts, local/Docker execution, CBMC options and bounded results |
| [Common usage](USAGE.md) | Shared CLI options, input/output rules and exit status |
| [Pipeline and diagnostics](PIPELINE.md) | Stages, success criteria, evidence checks and interpreting failures |
| [Limitations](LIMITATIONS.md) | Shared proof requirements, deductive inference boundaries and LLM coverage under investigation |
| [Release roadmap](../Roadmap.md) | Release targets and remaining qualification work |

The [project README](../README.md) summarizes workflows and provides a first Docker run.
The [ASE 2024 example](../examples/ase-2024/README.md) supplies a public input;
[regression cases](../tests/cases/README.md) record expected outcomes.
