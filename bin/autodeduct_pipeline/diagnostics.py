"""Classification of external tool stdout/stderr into stable diagnostics.

Every function here reads only captured tool output (or an exit code) and
turns it into an actionable, versioned message. AutoDeduct deliberately does
not scan C source text to guess which unsupported language feature a project
contains; the native tool diagnostics are authoritative.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .stages import StageResult


# Turn recurring compiler diagnostics into stable, actionable input messages.
def failure_diagnostic(*, returncode: int, stdout: str, stderr: str) -> str:
    streams = [line.strip() for stream in (stderr, stdout) for line in stream.splitlines()]
    combined = "\n".join(streams)

    entry_point = re.search(
        r"['\"](?P<name>[A-Za-z_]\w*)['\"] is not a defined function",
        combined,
        re.IGNORECASE,
    )
    if entry_point:
        name = entry_point.group("name")
        return (
            f"entry point '{name}' was not found as a function definition in the "
            "input C sources; check --entry-point and ensure the function is defined"
        )

    forward_declaration = re.search(
        r"implicit declaration of function\s+['\"](?P<name>[A-Za-z_]\w*)['\"]",
        combined,
        re.IGNORECASE,
    )
    if forward_declaration:
        name = forward_declaration.group("name")
        return (
            f"function '{name}' is called without a visible declaration; add a "
            "prototype in the source or an included header before running AutoDeduct"
        )

    missing_header = re.search(
        r"(?:fatal error|error):\s*['\"]?(?P<header>[^'\"\s:]+\.h)['\"]?\s*: "
        r"No such file or directory",
        combined,
        re.IGNORECASE,
    )
    if missing_header:
        header = missing_header.group("header")
        return (
            f"required header '{header}' was not found; add its directory with "
            "--include"
        )

    if re.search(r"unterminated (?:comment|string literal)", combined, re.IGNORECASE):
        return (
            "input contains an unterminated C or ACSL comment/string; check the "
            "source delimiters"
        )

    diagnostic = next(
        (
            line
            for line in streams
            if re.search(r"fatal error|user error|error:|aborted", line, re.IGNORECASE)
        ),
        streams[-1] if streams else "no diagnostic was written by the command",
    )
    return f"command exited with status {returncode}: {diagnostic}"


# Read only the captured tool output used for bounded diagnostic
# classification. AutoDeduct deliberately does not scan C source text to
# guess which unsupported language feature a project contains.
def stage_log_text(stage: StageResult, tool_name: str) -> tuple[str | None, str | None]:
    log_files = [path for path in (stage.stderr_file, stage.stdout_file) if path]
    if not log_files:
        return "", None
    try:
        return (
            "\n".join(
                Path(path).read_text(encoding="utf-8", errors="replace")
                for path in log_files
            ),
            None,
        )
    except OSError as error:
        return None, f"could not inspect {tool_name} logs: {error}"


# Remove common Frama-C/plugin severity prefixes before matching complete
# diagnostic phrases. Anchoring matches to the remaining line avoids treating
# explanatory prose such as "completed without a syntax error" as a failure.
def diagnostic_payload(line: str) -> str:
    payload = line.strip()
    prefix = re.compile(
        r"^(?:\[[^\]\r\n]+\]|user\s+error|fatal\s+error|warning|error)\s*:?\s*",
        re.IGNORECASE,
    )
    for _ in range(8):
        updated = prefix.sub("", payload, count=1)
        if updated == payload:
            break
        payload = updated
    return payload.casefold()


# Detect TriCera backend errors that Saida may otherwise hide behind a successful exit code.
def tricera_diagnostic(stage: StageResult) -> str | None:
    """Reject explicit backend failures hidden behind Saida exit status zero."""

    text, inspection_error = stage_log_text(stage, "Saida/TriCera")
    if inspection_error:
        return inspection_error
    assert text is not None
    for line in text.splitlines():
        payload = diagnostic_payload(line)
        unsupported_type = re.match(
            r"^(?:tricera\s*:?\s*)?type\s+(?P<type>.+?)\s+not\s+supported\b",
            payload,
        )
        if unsupported_type:
            type_name = unsupported_type.group("type")
            return (
                f"TriCera reported that type '{type_name}' is not supported; "
                "AutoDeduct V1 will not continue with a fallback type "
                "approximation"
            )
        if re.match(r"^(?:tricera\s*:?\s*)?syntax\s+error\b", payload):
            return (
                "TriCera reported a syntax error in its inference input; no "
                "sound functional contract was produced. Inspect the "
                "Saida/TriCera logs for the unsupported C or ACSL construct"
            )
        if re.match(r"^(?:tricera\s*:?\s*)?not\s+solvable\b", payload) or re.match(
            r"^[\w.$]*exception\s*:\s*not\s+solvable\b", payload
        ):
            return (
                "TriCera reported that the inference problem is not solvable; "
                "no sound functional contract was produced. Inspect the "
                "Saida/TriCera logs and provide the affected contract manually"
            )
    return None


# Preserve TriCera preprocessing fallbacks as visible warnings when Saida still
# writes an inferred source file. ISP, the reachable-contract check, and WP then
# determine whether the resulting proof is complete for the selected input.
def tricera_preprocessing_warning(stage: StageResult) -> str | None:
    text, inspection_error = stage_log_text(stage, "Saida/TriCera")
    if inspection_error:
        return inspection_error
    assert text is not None
    for line in text.splitlines():
        payload = diagnostic_payload(line)
        if payload.startswith("rosetta error:") or payload.startswith(
            "tricera preprocessor (tri-pp) returned an empty file"
        ):
            return (
                "TriCera preprocessing reported a fallback; continuing because "
                "Saida produced inferred.c. Review the Saida/TriCera logs and "
                "treat the run as successful only if ISP, contract checking, and "
                "WP also complete"
            )
    return None


# Surface Saida's explicit partial-frame warning while still allowing the
# mandatory downstream WP stage to establish the complete result.
def saida_partial_diagnostic(stage: StageResult) -> str | None:
    text, inspection_error = stage_log_text(stage, "Saida")
    if inspection_error:
        return inspection_error
    assert text is not None
    text = text.casefold()
    if "saida-w001" in text:
        return (
            "Saida preserved a function-level assigns clause without checking "
            "its frame condition; the final WP stage must prove it"
        )
    return None


# Convert ISP's native unsupported-pointer diagnostic into a stable V1
# boundary message. The native code is authoritative; no source regex is used.
def isp_limit_diagnostic(stage: StageResult) -> str | None:
    text, inspection_error = stage_log_text(stage, "ISP")
    if inspection_error:
        return inspection_error
    assert text is not None
    for line in text.splitlines():
        match = re.search(r"\bISP-E005\b(?P<detail>[^\r\n]*)", line, re.IGNORECASE)
        if match:
            detail = match.group("detail").lstrip(" ]:-")
            native_detail = f": {detail}" if detail else ""
            return (
                "ISP rejected an unsupported lvalue, pointer, or array-index "
                f"expression (ISP-E005{native_detail}). Simplify the access "
                "or provide and review the required ACSL validity, separation, "
                "frame, and value annotations manually; WP was not run"
            )
    return None


# ISP documents every ISP-Wxxx diagnostic as evidence that its generated
# auxiliary specification may be incomplete. Keep the diagnostic visible, then
# let contract checking and WP determine whether the selected run still proves.
def isp_partial_diagnostic(stage: StageResult) -> str | None:
    text, inspection_error = stage_log_text(stage, "ISP")
    if inspection_error:
        return inspection_error
    assert text is not None
    codes = sorted(set(re.findall(r"\bISP-W\d{3}\b", text, re.IGNORECASE)))
    if codes:
        return (
            "ISP reported partial auxiliary inference ("
            + ", ".join(code.upper() for code in codes)
            + "); review the input and generated annotations"
        )
    return None


# Recognize explicit WP evidence for missing or insufficient loop annotations.
# This runs only after WP has left goals unresolved, so successful loop goals
# elsewhere in the same log cannot misclassify an unrelated failure.
def wp_loop_diagnostic(text: str) -> bool:
    missing_annotation = re.compile(
        r"^(?:missing|no)\s+loop\s+(?:invariant|assigns|variant)\b"
        r"|^loop\s+(?:invariant|assigns|variant)\b[^\r\n]*\bmissing\b",
        re.IGNORECASE,
    )
    unresolved_loop_goal = re.compile(
        r"\[(?:timeout|unknown|failed|invalid)\][^\r\n]*"
        r"loop_(?:invariant|assigns|variant)(?:_[A-Za-z0-9]+)*\b",
        re.IGNORECASE,
    )
    return any(
        missing_annotation.search(diagnostic_payload(line))
        or unresolved_loop_goal.search(line)
        for line in text.splitlines()
    )


# Check that WP emitted a complete proved-goal summary before accepting verification.
def wp_diagnostic(stage: StageResult) -> str | None:
    """Require WP to print a complete proved-goal summary."""

    if not stage.stdout_file:
        return "WP did not produce a stdout log"
    try:
        stdout = Path(stage.stdout_file).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError as error:
        return f"could not inspect WP output: {error}"
    combined, inspection_error = stage_log_text(stage, "WP")
    if inspection_error:
        return inspection_error
    assert combined is not None
    matches = re.findall(r"Proved goals:\s*(\d+)\s*/\s*(\d+)", stdout)
    if not matches:
        return "WP did not produce a proved-goals summary"
    proved, total = (int(value) for value in matches[-1])
    if total == 0:
        return "WP generated no proof goals"
    if proved != total:
        if wp_loop_diagnostic(combined):
            return (
                f"WP proved {proved} of {total} goals; loop proof obligations "
                "remain unresolved or WP reported missing loop annotations. "
                "AutoDeduct V1 does not infer loop invariants: add and review "
                "loop invariant and loop assigns clauses, plus a loop variant "
                "when termination must be proved"
            )
        unresolved = re.findall(
            r"\[(?P<status>Timeout|Unknown|Failed|Invalid)\]\s+(?P<goal>[^\n]+)",
            stdout,
            re.IGNORECASE,
        )
        if unresolved:
            details = "; ".join(
                f"{status}: {goal.strip()}" for status, goal in unresolved
            )
            return f"WP proved {proved} of {total} goals; unresolved: {details}"
        return f"WP proved {proved} of {total} goals"
    return None


__all__ = [
    "failure_diagnostic",
    "stage_log_text",
    "diagnostic_payload",
    "tricera_diagnostic",
    "tricera_preprocessing_warning",
    "saida_partial_diagnostic",
    "isp_limit_diagnostic",
    "isp_partial_diagnostic",
    "wp_loop_diagnostic",
    "wp_diagnostic",
]
