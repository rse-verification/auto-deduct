# AutoDeduct 1.0 "Rubber Duck" Limitations

AutoDeduct 1.0 "Rubber Duck" is a deterministic CLI pipeline. It does not modify source
files or automatically accept generated contracts into the original project.
Its Saida, TriCera, and ISP components are experimental and retain their own
language and inference boundaries.

## Supported Input Shape

AutoDeduct 1.0 accepts one C translation unit plus its headers. Multiple `.c` inputs are
rejected before analysis because Saida's current source merge is not
file-aware.

Saida supports a C-expression subset of `requires`, `ensures`, and supported
behavior guards. General ACSL logic functions and predicates are outside this
inference subset. Behavior-specific `assigns`, `complete`, and `disjoint`
clauses are not treated as fully inferred and verified functional contracts.

## Known Boundaries

| Boundary | AutoDeduct 1.0 behavior | Recommended workaround |
| --- | --- | --- |
| Floating point | Functional inference fails when TriCera reports an unsupported floating-point type. An integer fallback is not accepted as equivalent semantics. | Use a reviewed fixed-point model or a toolchain that models the required IEEE behavior. |
| Pointer arithmetic and unsupported lvalues | ISP reports `ISP-E005`; WP is not run on incomplete auxiliary inference. | Simplify the access pattern or provide reviewed validity, separation, frame, and value-relation ACSL. |
| Nested pointers | May fail during functional inference, ISP, contract checking, or WP. AutoDeduct 1.0 does not infer a complete multi-level validity and aliasing model. | Flatten the interface where appropriate or write explicit contracts for every dereference level. |
| Persistent local static state | WP may remain incomplete, but no component diagnostic identifies every occurrence. | Model persistent state explicitly and provide an accurate frame and state-transition contract. |
| Loops | General loop-invariant inference is outside AutoDeduct 1.0. Missing or insufficient annotations leave WP goals unresolved. | Add reviewed `loop invariant`, `loop assigns`, and, where required, `loop variant` clauses. |

## ISP Aggregate and Index Boundaries

ISP supports flat struct fields after an enum-indexed array access. It does
not recursively generate annotations for arbitrary repeated `Field -> Index`
paths such as `records[slot].f1[i].f2[j]`.

- `ISP-E010` reports an unsupported nested aggregate path.
- `ISP-E011` reports an unbounded index or a concrete expansion exceeding
  1024 values.
- `ISP-E005` covers unsupported lvalue, pointer, and index expression shapes.

These diagnostics fail closed: AutoDeduct does not run WP as though the
missing auxiliary annotations were complete.

## Contracts and Frames

Saida preserves function-level `assigns` clauses, but its inference harness
does not by itself prove every frame condition. `SAIDA-W001` identifies this
partial check. AutoDeduct therefore requires the final WP stage to prove all
generated obligations before reporting success.

Missing contracts on functions ISP considers reachable fail the
`contract_check` stage. A contract that exists but is too weak may instead
appear as unresolved WP goals.

## Interpreting Success

A successful command is evidence for the selected input, entry point, tool
versions, and generated proof obligations. It is not evidence that all C or
ACSL language features are supported, or that every possible project using a
similar pattern will verify.

When qualifying a new program, retain `report.json` and the named stage logs.
The public regression sources under `tests/cases/` document the expected
outcomes exercised by the repository's integration suite.
