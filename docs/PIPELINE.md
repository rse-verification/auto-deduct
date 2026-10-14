# Pipeline and Diagnostics

[Documentation index](README.md) · [Common usage](USAGE.md) · [LLM usage](LLM.md)

AutoDeduct coordinates existing analysis components. It does not implement a
C parser, call graph, abstract interpreter, or theorem prover itself.

## Stage Flow

The following stages apply to the default deterministic mode.

| Stage | Component | Responsibility | Main artifact |
| --- | --- | --- | --- |
| `parse` | Frama-C | Parse and type-check the selected C translation unit. | parse logs |
| `saida_tricera` | Saida and TriCera | Infer functional ACSL contracts. | `inferred.c` |
| `isp_eva` | ISP and Eva | Infer auxiliary annotations from abstract states. | `out.c` |
| `contract_check` | ISP | Report reachable helper functions without contracts. | `missing-helper-contracts.json` |
| `wp` | Frama-C WP and provers | Generate and discharge proof obligations. | WP logs |

Saida is the Frama-C integration plugin that invokes TriCera. ISP consumes the
annotated C output and uses Eva states to produce additional ACSL clauses. ISP
also owns reachable-function and missing-contract semantics; AutoDeduct reads
its JSON report rather than reimplementing the call graph.

With `--mode llm --llm-runtime docker`, `logos_image` resolves the installed
verifier image to an immutable ID, then `logos_skill` extracts its SKILL.md for
the host agent. These two stages are unnecessary in local mode, which uses the
configured host skill. `logos_environment` checks wrapper dependencies for the
selected runtime. `llm_workflow` then invokes Codex with the selected SKILL.md
and a generation-only task on the host. `logos_verify` explicitly invokes the
LOGOS Python wrapper locally or inside Docker for annotation and verification.
`skill_verify` validates the returned WP evidence without rerunning WP.
AutoDeduct checks source hashes, annotation-only changes, the requested
verification options, and complete nonzero proof goals. Saida/TriCera,
ISP/Eva, and ISP coverage checking are not run. See [LLM mode](USAGE.md#llm-mode).

## Status Model

The JSON top-level status is `passed` or `failed`; the console prints uppercase
labels. Each recorded JSON stage has
one of these statuses:

- `passed`: the mandatory stage completed and its expected output is valid.
- `warning`: the stage reported a recognized non-fatal limitation; the
  diagnostic is retained and later stages continue.
- `failed`: the command returned a nonzero status, produced an unusable
  artifact, or did not meet an acceptance condition.
- `error`: the command could not be started.
- `timeout`: the command exceeded its configured stage timeout.

Stages not reached after an earlier failure are omitted from the `stages`
array rather than emitted as `skipped` records.

A warning is not silently accepted. It remains visible in the console and
`report.json`, while later contract checks and WP determine whether the
program can still be completely verified.

## Acceptance Criteria

In deterministic mode, AutoDeduct returns exit code `0` only when:

1. the input and environment are valid;
2. parsing succeeds;
3. Saida/TriCera and ISP produce their expected generated files;
4. ISP reports no reachable helper function with a missing contract; and
5. WP reports proof goals and proves all of them.

In LLM mode, the host skill must return source-matched contract JSON, and the
LOGOS wrapper must finish with annotation-only output and a verifier report
with all requested
options and complete nonzero WP goals. The result does not include the
deterministic mode's reachable-helper coverage guarantee.

A command exiting successfully is not enough by itself. AutoDeduct validates
the generated artifacts, machine-readable contract report, and WP goal count.
A WP run containing no goals is rejected.

The default WP stage proves generated contract obligations only. It does not
claim absence of runtime errors. With `--wp-rte`, WP also generates
runtime-error obligations and every added goal must pass for AutoDeduct to
return exit code `0`.

## Failure Flow

An input, environment, parse, semantic inference, contract, timeout, or WP
failure returns exit code `1`. The human summary identifies the responsible
stage and points to its log. Later stages are not run, and are omitted from
the report, when their input cannot be trusted.

Examples:

- A missing source path fails during input validation.
- An unknown entry function reports the requested function name and suggests
  checking `--entry-point`.
- A missing visible C prototype is reported as a parse problem.
- Missing reachable contracts fail `contract_check` even if a process exits
  with status zero.
- Unresolved WP goals report the proved/total count and available goal names.

## Diagnostic Policy

Diagnostics come from explicit process output, native plugin codes, generated
artifact validation, and unresolved WP obligations. AutoDeduct does not scan C
source text to guess a failure cause.

Recognized TriCera preprocessing fallback output is retained as a warning when
Saida still writes a usable `inferred.c`. Explicit syntax, unsolvable, or
unsupported-type diagnostics fail functional inference even if the process
returns zero.

ISP `ISP-Wxxx` diagnostics are retained as warnings and WP continues. ISP
`ISP-Exxx` diagnostics stop the pipeline because required auxiliary inference
was not safely completed. Detailed feature boundaries and workarounds are in
[Release limitations](LIMITATIONS.md).

## Inspecting Results

Start with `report.json`, then inspect the corresponding stage logs. The most
useful generated files are:

- `inferred.c` for the functional contracts returned through Saida/TriCera;
- `out.c` for the source passed to WP after ISP;
- `missing-helper-contracts.json` for ISP reachability and contract coverage;
- `report.json` for commands, statuses, diagnostics, log paths, and artifacts.

Every report contains `schema_version`. This branch writes schema version
`1`; the separate `version` field identifies the AutoDeduct CLI release.
AutoDeduct 1.1 adds `mode` to schema version `1`; consumers of earlier reports
may treat its absence as `deterministic`.

Use `autodeduct --json ...` when another program or CI job needs the same
result as machine-readable standard output.
