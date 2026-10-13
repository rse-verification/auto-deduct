"""Delegate the entire LLM workflow to a local skill and inspect its evidence."""

import hashlib
import json
import re
import shlex
from difflib import SequenceMatcher
from pathlib import Path

from .diagnostics import wp_diagnostic
from .stages import PipelineError, SAIDA_OUTPUT, StageResult, command_options, run_stage


def command_words(value):
    try:
        words = shlex.split(value or "")
    except ValueError as error:
        raise PipelineError("input", f"invalid Codex runner command: {error}") from error
    if not words:
        raise PipelineError("input", "LLM mode requires a configured Codex runner command")
    return words


def validate_llm_options(args, output_dir):
    if args.mode != "llm":
        return
    if not args.llm_skill or not Path(args.llm_skill).expanduser().is_file():
        raise PipelineError("input", "set --llm-skill or AUTODEDUCT_LLM_SKILL to an installed SKILL.md")
    for word in [str(Path(args.llm_skill).expanduser().resolve()), *command_words(args.llm_runner)]:
        # Bare command names and CLI arguments are not files in the current directory.
        if not Path(word).expanduser().is_file():
            continue
        path = Path(word).expanduser().resolve()
        if path == output_dir or output_dir in path.parents:
            raise PipelineError("input", "skill and runner files must be outside the output directory")
        if Path(word).is_file() and not Path(word).is_absolute():
            raise PipelineError("input", "use absolute paths for runner scripts and files")


def validate_contracts(path, source_text):
    bundle = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(bundle, dict) or bundle.get("format") != "acsl-contracts-v2":
        raise ValueError("expected an acsl-contracts-v2 JSON object")
    if not isinstance(bundle.get("contracts"), dict):
        raise ValueError("contracts must be an object")
    metadata = bundle.get("metadata")
    digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    if not isinstance(metadata, dict) or metadata.get("source_sha256") != digest:
        raise ValueError("contracts must contain metadata.source_sha256 matching the input source")


def validate_annotation_only(source, annotated):
    """Accept only complete ACSL block insertions between original source lines."""
    source = source.rstrip() + "\n"
    annotated = annotated.rstrip() + "\n"
    original_lines = source.splitlines(keepends=True)
    generated_lines = annotated.splitlines(keepends=True)
    # Locate comments/strings so inserted annotations cannot split an existing token.
    tokens = list(re.finditer(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', source, re.S))
    # ponytail: conservative line diff can be quadratic; use an AST comparison
    # if large generated files or source-preserving reformatting become necessary.
    for tag, start, end, added_start, added_end in SequenceMatcher(
        None, original_lines, generated_lines, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        offset = sum(map(len, original_lines[:start]))
        inserted = "".join(generated_lines[added_start:added_end])
        if (
            tag != "insert"
            or any(token.start() < offset < token.end() for token in tokens)
            or (start and original_lines[start - 1].rstrip("\r\n").endswith("\\"))
            or not re.fullmatch(r'(?:\s*/\*@(?:(?!\*/).)*\*/[ \t]*\n)+', inserted, re.S)
        ):
            raise ValueError("annotation provider changed existing source or annotations; only ACSL block insertions are allowed")


def run_skill_workflow(args, source, output_dir, report):
    try:
        source_text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        report.errors.append({"stage": "llm_contracts", "message": str(error)})
        return report
    contracts = output_dir / "llm-contracts.json"
    annotated = output_dir / SAIDA_OUTPUT
    evidence_file = output_dir / "llm-verification.json"
    skill = Path(args.llm_skill).expanduser().resolve()
    options = [*command_options(args, [source]), *args.wp_option]
    if args.wp_rte:
        options.append("-wp-rte")
    task_file = output_dir / "llm-task.json"
    task_file.write_text(json.dumps({
        "skill": str(skill), "source": str(source),
        "contracts": str(contracts), "annotated_source": str(annotated),
        "verification_json": str(evidence_file), "verification_options": options,
    }, indent=2) + "\n", encoding="utf-8")
    prompt = (
        f"Use the skill at {json.dumps(str(skill))}. Read its complete SKILL.md and "
        f"follow its workflow on the task in {json.dumps(str(task_file))}. "
        "You are explicitly requested to complete generation AND verification. "
        "Author the structured contracts yourself following the skill; do not use a "
        "separate generator with built-in prompts. Use the skill repository's Python "
        "wrapper to apply contracts and run --verify with --verification-json set to "
        "verification_json. Pass every verification_options item using a repeated "
        "--frama-c-option=VALUE. The wrapper must write the verification evidence; "
        "do not author or edit that JSON yourself. Use exactly the supplied artifact "
        "paths. Preserve the original source and all existing specifications. Write "
        "only in the task output directory; do not modify the skill repository. "
        "If dependencies or permissions are unavailable, report the failure. "
        "Do not weaken the requested proof or substitute a different verifier."
    )
    runner = command_words(args.llm_runner)
    # Codex's automatic approval mode already selects workspace-write.
    sandbox = [] if "--approve-for-me" in runner else ["--sandbox", "workspace-write"]
    workflow = run_stage(
        name="llm_workflow", description="Run the configured skill, including verification",
        command=[*runner, "--cd", str(output_dir),
                 "--skip-git-repo-check", *sandbox, "--json",
                 "--output-last-message", str(output_dir / "llm-final.txt"), prompt],
        cwd=output_dir, output_dir=output_dir, timeout=args.timeout, artifact=evidence_file,
    )
    report.stages.append(workflow)
    if workflow.status != "passed":
        report.errors.append({"stage": workflow.name, "message": workflow.error or "skill runner failed"})
        return report
    verification = StageResult(
        name="skill_verify", description="Validate the skill's WP evidence (no second verifier run)",
        status="failed", artifact=str(evidence_file),
    )
    report.stages.append(verification)
    try:
        validate_contracts(contracts, source_text)
        if source.read_text(encoding="utf-8") != source_text:
            raise ValueError("skill changed the original input source")
        validate_annotation_only(source_text, annotated.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
        if not isinstance(evidence, dict) or evidence.get("schema_version") != 1:
            raise ValueError("skill must produce a version-1 verification report")
        if evidence.get("source_sha256") != hashlib.sha256(annotated.read_bytes()).hexdigest():
            raise ValueError("verification report does not match the annotated source")
        command = evidence.get("command")
        if not isinstance(command, list) or not command or command[1:] != [*options, "-wp", str(annotated)]:
            raise ValueError("skill verification did not use the requested source and proof options")
        verification.command = command
        if type(evidence.get("returncode")) is not int:
            raise ValueError("verification report must contain an integer returncode")
        verification.returncode = evidence["returncode"]
        for stream in ("stdout", "stderr"):
            if not isinstance(evidence.get(stream), str):
                raise ValueError(f"verification report must contain {stream}")
            path = output_dir / f"skill_verify.{stream}.log"
            path.write_text(evidence[stream], encoding="utf-8")
            setattr(verification, f"{stream}_file", str(path))
        if verification.returncode != 0:
            raise ValueError(f"skill verifier exited with status {verification.returncode}")
        problem = wp_diagnostic(verification)
        if problem:
            raise ValueError(problem)
    except (OSError, ValueError) as error:
        verification.error = str(error)
        report.errors.append({"stage": verification.name, "message": str(error)})
        return report
    verification.status = "passed"
    report.status = "passed"
    return report
