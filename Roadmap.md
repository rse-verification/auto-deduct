# Roadmap

This is a living document describing the target for each AutoDeduct release.

## AutoDeduct 1.0 "Rubber Duck"

- Provide a reproducible Docker image with pinned versions of Frama-C, Saida,
  TriCera, ISP, OCaml, and the configured WP provers.
- Provide the `autodeduct` command-line pipeline and machine-readable
  `report.json` output.
- Keep generated artifacts separate from the input source.
- Define the supported C and ACSL subset and report unsupported constructs
  explicitly.
- Check reachable-helper contract coverage before WP.
- Support optional WP runtime-error obligations through `--wp-rte`.
- Exercise the public ASE 2024 example and categorized microtests in CI.

### Acceptance Criteria

- The Docker image builds from a clean checkout.
- Unit tests and the public Docker regression matrix pass.
- The CLI returns `PASSED` only when every mandatory stage and WP goal passes;
  otherwise it returns `FAILED` with stage-specific diagnostics.
- The input source remains unchanged.

## AutoDeduct V2 “Double Ducks” — release candidate

- Add explicit `deductive` and `llm` mode commands while keeping existing flags.
- Use host Codex/LOGOS for contract generation, followed by launcher-owned
  annotation and WP evidence validation.
- Offer local verification and optional Docker verification without container
  Codex or model credentials in the verifier image.
- Keep setup, mode-specific usage, common CLI reference and limitations in
  separate [documentation guides](docs/README.md).

Complete native host verification and native Windows Frama-C qualification
remain open. The LLM workflow remains experimental and does not provide the
traditional ISP helper-coverage check.
Its C/ACSL feature coverage and contract-generation reliability remain under
investigation; see the [mode-specific limitations](docs/LIMITATIONS.md).

## Future Releases

- Broaden the supported C and ACSL subsets based on reviewed use cases.
- Improve inferred-contract quality and proof diagnostics.
- Evaluate tighter Frama-C integration when it provides additional user value.
