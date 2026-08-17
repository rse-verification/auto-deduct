# Paper 1046 Example

This directory contains a public example derived from the companion material
for:

> Mingxing Liu, Junfeng Wang, Tao Lin, Quan Ma, Zhiyang Fang, and Yanqun Wu,
> "An Empirical Study of the Code Generation of Safety-Critical Software
> Using LLMs," *Applied Sciences*, 14(3), 1046, 2024.

Paper: <https://doi.org/10.3390/app14031046>

Public companion repository:
<https://github.com/lmxstar/GPT-prompts-for-safety-critical-software>

## Contents

* `cruise_control/CC-simple.c` is the authors' public CruiseControl example
  from the companion archive. It is kept unchanged.
* `cruise_control/harness.c` is an AutoDeduct-specific wrapper. It renames the
  example's `main` function and adds the ACSL contract on `paper_entry`.
* The example uses the standard C header `<stdio.h>` only. No private or
  Scania-specific header is included.
* `LICENSE-GPL-3.0.txt` is the license from the public companion repository.

This directory contains no Scania case-study source. The harness is separate
so that the public source remains unchanged and the AutoDeduct input contract
is explicit.

## Run with AutoDeduct

From the repository root, with the V1 Docker image already built:

```shell
mkdir -p examples/paper-1046/cruise_control/autodeduct-output

docker run --rm --platform linux/amd64 \
  -v "$PWD":/work \
  -w /work \
  auto-deduct:v1 \
  autodeduct \
  --entry-point paper_entry \
  --output-dir /work/examples/paper-1046/cruise_control/autodeduct-output \
  examples/paper-1046/cruise_control/harness.c
```

The result is a useful contract-propagation example, not a release smoke test.
Inspect `missing-helper-contracts.json`, `contracts.json`, `out.c`, and the
stage logs to see what ISP reports and what WP can prove for this input.

The public source and the harness are distributed under separate notices:
see `LICENSE-GPL-3.0.txt` for the public companion material and the repository
`LICENSE` for AutoDeduct itself.
