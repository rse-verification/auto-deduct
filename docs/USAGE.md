# Common usage

[Documentation index](README.md) · [Deductive mode](DEDUCTIVE.md) · [LLM mode](LLM.md)

## Select a mode

```text
autodeduct --help
autodeduct --version
autodeduct deductive [options] SOURCE_OR_DIRECTORY
autodeduct llm [options] SOURCE_OR_DIRECTORY
autodeduct acta [options] SOURCE_OR_DIRECTORY
```

These commands assume `bin/` is on the host `PATH`; use `./bin/autodeduct` from
the checkout otherwise. The traditional Docker command is shown in
[deductive usage](DEDUCTIVE.md#run-in-docker).

Mode-specific guides:

- [Deductive mode](DEDUCTIVE.md): Docker, local execution, outputs and manual stages.
- [LLM mode](LLM.md): host setup, local versus Docker verification, Codex profiles,
  contract JSON handoff and reports.
- [AcTa/CBMC mode](ACTA.md): existing entry contracts, local/Docker execution,
  CBMC options, loop bounds and evidence.

The default is deductive. `--mode deductive`, `--mode llm`, and `--mode acta`
flags are alternatives to the mode commands; choose one form. Reports use
`mode: "deductive"` for deductive mode, `mode: "llm"` for LLM mode, and
`mode: "acta"` for AcTa mode.
There is no automatic fallback between modes. Use `./llm` or `./deductive` for
input directories with those names; use `./acta` for a directory named `acta`.

## Common options

| Option | Purpose |
| --- | --- |
| `--entry-point NAME` | Contracted entry function; default `main` |
| `--output-dir DIRECTORY` | Generated files and logs; default `autodeduct-output` |
| `--include DIRECTORY` | Header directory; repeat as needed |
| `--frama-c-option OPTION` | Extra Frama-C argument; repeat as needed |
| `--wp-option OPTION` | Extra WP argument; repeat as needed |
| `--wp-rte` | Add runtime-error goals; all added goals must be proved |
| `--timeout SECONDS` | Positive timeout for each external stage; default 300 seconds |
| `--json` | Print the final machine-readable report |

Pass options starting with `-` using `=`:

```shell
autodeduct deductive --include include \
  --frama-c-option=-cpp-extra-args=-DPLATFORM_TEST path/to/program.c
```

Pipeline-owned arguments such as `-main`, `-wp`, `-saida`, `-isp` and `-acta` cannot be
changed through forwarded options. Use AutoDeduct's dedicated options.

## Input and output rules

AutoDeduct accepts one `.c`/`.C` translation unit or a directory containing
exactly one. Directory searches ignore common version-control, build,
dependency and generated-output folders. Multiple C inputs are rejected;
provide one analysis translation unit and its headers with `--include`.
Headers are not source inputs.

Use a separate output directory. It must not contain input files or overlap a
selected source directory. For LLM mode, the skill and runner files must also
be outside it. Known artifacts from an earlier valid run are cleared so stale
reports cannot count as a current proof.

## Results and exit status

Exit `0` means every mandatory stage and all nonzero WP goals passed, or AcTa
generated a harness and CBMC reported all properties successful, including at
least one entry-contract assertion and any unwinding assertions. Exit `1`
means input, environment, generation or verification failed. Argument parsing
errors use exit `2`. Retain `report.json` and stage logs for diagnosis.

See [pipeline and diagnostics](PIPELINE.md) for stage status, evidence validation
and proof assumptions, and [limitations](LIMITATIONS.md) for unsupported inputs.

## LLM mode

See the dedicated [LLM setup and usage guide](LLM.md).

| Option | Purpose |
| --- | --- |
| `--llm-runtime local\|docker` | Where the LOGOS wrapper verifies; default `local`, with Codex on the host in both cases |
| `--llm-docker-image IMAGE` | Existing local verifier image name:tag or ID; default `auto-deduct:latest`; no automatic build or pull |
| `--llm-docker-platform PLATFORM` | Verifier architecture; default `linux/amd64` |

If you build with a custom image name, pass that name to the launcher. See
the [matching build and run commands](LLM.md#choose-a-custom-image-name).

## Docker

See [deductive Docker usage](DEDUCTIVE.md#run-in-docker) or
[LLM Docker verification](LLM.md#run-with-docker-verification), or
[AcTa/CBMC Docker usage](ACTA.md#docker-from-the-host-launcher).

## Without Docker

See [deductive local usage](DEDUCTIVE.md#run-locally) or
[LLM local verification](LLM.md#local-verification-dependencies), or
[AcTa/CBMC local setup](ACTA.md#without-docker).
