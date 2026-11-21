# Generated helper frame repair

Agent mode repairs a generated contracts-JSON entry whose assigns list is exactly
`["\\everything"]` by omitting that entry. This leaves effects unconstrained;
it does not assert purity. The input source and its existing ACSL are untouched.
`helper-repairs.json` records the function and repair. Normal verifier validation
still runs afterward; a successful process exit does not establish all WP goals.

SpecBridge prepares additional supporting helper/reader ACSL on copies before
handoff and records it in `automatic-support.json`. Those contracts create body
and caller obligations. They do not establish external implementations, startup,
concurrency, target ABI or requirement intent. Failed, timeout and unknown goals
remain unproved. Unreachable goal counts require reachability review.
