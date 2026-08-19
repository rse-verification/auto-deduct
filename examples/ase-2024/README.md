# ASE 2024 Steering Example

This directory contains the public steering-system example used with the
AutoDeduct research work. The source is copied from the
[rse-verification/auto-deduct-examples](https://github.com/rse-verification/auto-deduct-examples/tree/main/ase-2024)
repository and is retained here with its original attribution.

The example is associated with the ASE 2024 paper:

> Jesper Amilon, Dilian Gurov, Christian Lidstrom, Mattias Nyberg, Gustav Ung,
> and Ola Wingbrant, "An Exercise in Mind Reading: Automatic Contract
> Inference for Frama-C", ASE 2024.
>
> [Paper record and DOI](https://doi.org/10.1007/978-3-031-55608-1_13)

stee.c models a vehicle steering system. Its ACSL contract is attached to
the module entry point main and expresses five requirements about primary
steering failure, vehicle movement, secondary steering, and electric-motor
activation. The helper functions are intentionally left without complete
contracts so that AutoDeduct can infer them.

The source has no separate header file. It uses void main() because that is
how it is published in the research example; this is accepted as the
Frama-C entry point for this case study.

## Run in the V1 Docker image

From the AutoDeduct repository root, after building the image:

```sh
docker run --rm \
  -v "$PWD":/work \
  -w /work \
  auto-deduct:latest \
  autodeduct \
  --entry-point main \
  --output-dir /work/examples/ase-2024/autodeduct-output \
  /work/examples/ase-2024
```

The input directory contains only stee.c, but using a directory demonstrates
that the V1 CLI accepts a project folder and keeps the example's source
layout. Stage logs and report.json are written below
examples/ase-2024/autodeduct-output/.

The upstream source is distributed from the public
auto-deduct-examples repository under GPL-2.0. The AutoDeduct repository
contains the corresponding project license.
