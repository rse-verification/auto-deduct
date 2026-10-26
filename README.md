# AutoDeduct V2 “Double Ducks”

**Release candidate.** AutoDeduct generates and verifies ACSL contracts for C
programs. Choose deductive inference, LLM-assisted contract generation, or
bounded verification of existing contracts with AcTa and CBMC.

AutoDeduct accepts one C translation unit and its headers. Generated files and
reports go into a separate output directory; the original source stays unchanged.

## Choose a workflow

| Workflow | What it does | Setup and usage |
| --- | --- | --- |
| `deductive` (default) | Infers contracts with Saida/TriCera and ISP/Eva, then checks them with Frama-C WP | [Deductive guide](docs/DEDUCTIVE.md) |
| `llm` | Generates contracts with host Codex using [LOGOS](https://github.com/rse-verification/logos), then checks them with Frama-C WP | [LLM guide](docs/LLM.md) · [Platform quickstart](docs/LLM_DOCKER_QUICKSTART.md) |
| `acta` | Uses [AcTa](https://github.com/rse-verification/AcTa) to generate a harness from an existing entry contract and check it with CBMC | [AcTa/CBMC guide](docs/ACTA.md) |

All three workflows support local tools or the same standard Docker image.
The image includes AcTa and CBMC by default and uses Frama-C 33 throughout.
LLM mode runs Codex on the host in both cases.

## Quick start: deductive verification in Docker

Requires Git, Docker running Linux containers, and a `GH_TOKEN` with read access
to AcTa; see [build credentials](docs/INSTALLATION.md#github-access-for-image-builds).
Use Bash/Zsh, or Ubuntu inside WSL 2 on Windows. The current standard toolchain targets `linux/amd64`.

```shell
git clone --branch acta-integration https://github.com/rse-verification/auto-deduct.git
cd auto-deduct

docker build --secret id=github_token,env=GH_TOKEN --platform linux/amd64 \
  -t auto-deduct:latest -f Dockerfiles/AutoDeductDockerfile .

docker run --rm --platform linux/amd64 \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/work" -w /work auto-deduct:latest \
  autodeduct deductive examples/ase-2024/stee.c \
  --output-dir /work/autodeduct-output
```

Inspect `autodeduct-output/report.json` and the stage logs. The
[example guide](examples/ase-2024/README.md) explains the public input and its
provenance. For native installation, custom images or proxy settings, see
[Installation](docs/INSTALLATION.md).

For **LLM generation**, follow the
[Windows/WSL 2, Ubuntu or macOS quickstart](docs/LLM_DOCKER_QUICKSTART.md).
For **AcTa/CBMC**, follow the [local or Docker setup](docs/ACTA.md).

## Results and scope

Verification runs write `report.json`, stage logs and workflow-specific artifacts:

- **Deductive and LLM:** generated annotations and WP verification results.
- **AcTa:** the generated harness, AcTa's JSON report and raw CBMC output.

Success means the selected workflow's required checks passed. WP workflows
require complete nonzero proof goals; AcTa checks the harness with CBMC and
unwinding assertions. Results depend on the specifications, assumptions and
supported features. Generated contracts and bounded results need review.

See [reports and diagnostics](docs/PIPELINE.md),
[supported inputs and limitations](docs/LIMITATIONS.md), and
[regression examples](tests/cases/README.md).

## Documentation

- [Installation](docs/INSTALLATION.md) — Docker images, host launcher and native tools.
- [CLI reference](docs/USAGE.md) — modes, options, inputs and exit status.
- [Documentation index](docs/README.md) — all workflow and report guides.
- [Release roadmap](Roadmap.md) — qualification work and planned releases.

## License

AutoDeduct is provided under the GNU GPLv2. See [LICENSE](LICENSE).
