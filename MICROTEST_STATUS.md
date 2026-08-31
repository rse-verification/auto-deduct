# AutoDeduct Microtest Status

Status date: 2026-08-31

## How to read this report

The AutoDeduct microtest corpus used by the assessment is on the separate
`autodeduct-support-microtests` branch under `autodeduct-support/micro-tests`.
The final `auto-deduct` branch now copies twelve public assessment sources into
`tests/cases/` and runs them as categorized Docker regressions: six complete
proofs, one warning followed by a complete proof, three safe functional
boundaries, and two incomplete WP cases. The remaining assessment rows are
still historical evidence until they receive their own current expected-outcome
tests.

This report uses four states:

| State | Meaning |
| --- | --- |
| Confirmed component support | The relevant current component was rebuilt and its focused regression test passed. |
| Historical pass | The assessment PDF reported a complete successful chain, but the test has not yet been rerun against the final image. |
| Safe limitation | The tool reports a clear limitation rather than claiming a complete inferred contract. |
| Open or unverified | The case is not fixed end to end, or current evidence is insufficient to claim that it is fixed. |

## Versions checked

| Component | Revision checked | Result |
| --- | --- | --- |
| AutoDeduct | `auto-deduct` at `df85ac8`, plus the current warning-handling change | The existing Docker toolchain ran the mounted working-tree CLI successfully. |
| TriCera | upstream master `96042c2` | Built successfully inside the new AutoDeduct image. |
| Saida | `v0.5.0` | Built as part of the image. |
| ISP | master `a538c4e` | Built as part of the image; its ptest suite passed. |

The updated Docker image proves that the component versions are compatible at
build time. It does not by itself prove every microtest end to end.

## Fresh pipeline evidence

The included public ASE example was run with the current CLI mounted into the
existing `auto-deduct:tricera-master-96042` image:

1. Frama-C parsing passed.
2. Saida/TriCera inference passed. The earlier TriCera preprocessor-fallback
   failure no longer occurred after updating to `96042c2`.
3. ISP/Eva reported `ISP-W002`, which says that some unreachable statements
   did not receive propagated auxiliary annotations.
4. ISP's reachable-contract check passed with no missing contracts.
5. WP passed.

`ISP-W002` is now a visible non-blocking warning: AutoDeduct continues to the
reachable-contract check and WP. A complete WP proof with no missing reachable
contracts is still required for a successful result. This avoids discarding a
valid proof merely because an optional auxiliary annotation was not generated.

## Microtest status by pattern

| Microtest or pattern | Current status | Explanation |
| --- | --- | --- |
| `supported/int_if_helper.c` | Confirmed end to end | Current V1 image passes the unchanged source. |
| Basic struct field helper | Confirmed end to end | Current V1 image passes `helper_struct_basic.c`. |
| Enum and switch helper | Confirmed end to end with warning | Current V1 image passes `helper_enum_switch_basic.c` with `-lib-entry`; ISP-W002 remains visible but WP is complete. |
| Side effect with `assigns` and `\old` | Confirmed end to end | Current V1 image passes `helper_assigns_old_basic.c` with `-lib-entry`. |
| Two-level call chain | Confirmed end to end | Current V1 image passes `helper_two_level_call_chain.c` with `-lib-entry`. |
| Same helper in two call contexts | Confirmed end to end | Current V1 image passes `helper_multiple_call_contexts.c`. |
| Whole-struct return | Confirmed end to end | Current V1 image passes `helper_struct_return_whole.c` with `-lib-entry`. |
| Scalar return rewrite | Historical pass | The PDF reported complete verification after the documented source-level rewrite. |
| Enum-indexed array, whole-struct return | Confirmed component support | TriCera master has a passing `enum-indexed-struct.c` regression and ISP master has enum-indexed struct ptests. The exact AutoDeduct microtest has not yet been rerun end to end. |
| Enum-indexed scalar struct field | Confirmed component support with a qualification | TriCera default reconstruction proves safety but can infer only the input restriction. With `-solutionReconstruction:wp`, it infers `records[1].level == \result`. AutoDeduct does not yet select this option. |
| Fixed integer-indexed struct field | Open or unverified | ISP supports selected bounded index paths, but this exact end-to-end microtest has not been rerun with current TriCera. |
| Integer-indexed array of structs, whole return | Open or unverified | The PDF identified ISP as the previous boundary. Current ISP preserves basic index identity but does not prove full general aggregate support. |
| Dynamic scalar-array read | Open or unverified | The PDF left one WP goal unresolved. No fresh complete run exists. |
| Fixed array-of-struct scalar read | Open or unverified | The PDF left one WP goal unresolved. No fresh complete run exists. |
| Single global struct scalar read | Open or unverified | The PDF left two WP goals unresolved. No fresh complete run exists. |
| Dynamic global-array update | Open or unverified | The PDF left two WP goals unresolved. A fixed-index rewrite is evidence about a changed input, not a general tool fix. |
| Valid pointer store | Open | The experimental TriCera fork branch is not in upstream master and has not been integrated into AutoDeduct. |
| Entry local stack pointer | Open | A rewrite exists in the assessment corpus, but the original interface shape has not been freshly verified end to end. |
| ACSL logic function | Open | The ISP logic-definition branch only avoids a plugin warning for defined logic bodies. It does not solve Saida/TriCera inference for all logic functions. |
| ACSL behavior contract | Open | The documented plain-ensures rewrite is a changed input, not native behavior-contract support. |
| ACSL predicate | Open | The documented inline rewrite is a changed input, not native predicate support. |
| Persistent local static state | Confirmed incomplete-WP boundary | Current V1 regression reports the missing `next_count` contract and incomplete WP proof. Model the state explicitly in a reviewed contract. |
| Floating-point arithmetic | Confirmed safe functional boundary | Current V1 regression reports that TriCera does not support `float` and rejects the fallback. |
| Pointer arithmetic | Confirmed safe functional boundary | Current V1 regression stops at TriCera's functional-input syntax boundary. |
| Nested pointer store | Confirmed safe functional boundary | Current V1 regression stops at TriCera's functional-input syntax boundary; V1 does not infer the required multi-level validity, aliasing, and frame model. |
| Loop without an invariant | Confirmed incomplete-WP boundary | Current V1 regression reaches WP but leaves loop-related obligations unresolved. Add reviewed loop annotations. |
| Missing forward declaration | Open or unverified | This is an input/preprocessing configuration issue. The final CLI must be rerun on the case with the required declarations and include options. |

## ISP-specific coverage

ISP master has focused regression tests for the parts it owns:

| ISP tests | Meaning |
| --- | --- |
| `isp_040` and `isp_041` | Conditional and repeated pointer mutation annotations, including the original CDL-2651 area. |
| `isp_045`, `isp_047`, and `isp_048` | Enum-indexed structs and direct constant/enum-indexed struct fields. |
| `isp_046` | Nested array/struct access is reported as an explicit limitation. |
| `isp_049`, `isp_050`, and `isp_051` | Bounded expansion, too-wide expansion, and unbounded-index handling. |

Three tested but unmerged ISP branches add small improvements:

1. `cdl-2651-isp-pure-logic-validation`: preserve defined ACSL logic and
   predicate bodies without a false global-annotation warning.
2. `cdl-2651-isp-index-expansion-boundary-tests`: cover signed intervals and
   declared-array-extent boundary cases.
3. `cdl-2651-isp-diagnostics-docs`: clarify the meaning of standalone ISP
   warnings versus AutoDeduct's fail-closed policy.

They should be rebased onto ISP master before merge. They improve diagnosis and
boundary handling; none makes the unsupported functional cases above fully
supported.

## Recommended next step

The twelve categorized public cases are now copied into the final AutoDeduct
repository as Docker integration regressions. Expand the suite with the
remaining public assessment corpus, with one expected outcome per test:

* complete success with proof-goal count;
* expected safe limitation and diagnostic code; or
* known open case.

That will turn the historical PDF into repeatable release evidence and prevent
a rewrite-based workaround from being mistaken for a general capability.
