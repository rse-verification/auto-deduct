"""Run host contract generation, then invoke LOGOS and validate WP evidence."""

import copy
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import uuid
from difflib import SequenceMatcher
from pathlib import Path

from .diagnostics import wp_diagnostic
from .runtime import (docker_run_options, in_container, resolve_image,
                      run_container_stage, validate_mount_path)
from .stages import PipelineError, SAIDA_OUTPUT, StageResult, command_options, run_stage, write_text


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
    if in_container():
        raise PipelineError("input", "LLM mode must be launched on the host; running Codex inside containers is unsupported")
    if args.llm_runtime == "local" and (not args.llm_skill or not Path(args.llm_skill).expanduser().is_file()):
        raise PipelineError("input", "set --llm-skill or AUTODEDUCT_LLM_SKILL to an installed SKILL.md")
    protected = command_words(args.llm_runner)
    if args.llm_runtime == "local":
        protected.append(str(Path(args.llm_skill).expanduser().resolve()))
    for word in protected:
        # Bare command names and CLI arguments are not files in the current directory.
        if not Path(word).expanduser().is_file():
            continue
        path = Path(word).expanduser().resolve()
        if path == output_dir or output_dir in path.parents:
            raise PipelineError("input", "skill and runner files must be outside the output directory")
        if Path(word).is_file() and not Path(word).is_absolute():
            raise PipelineError("input", "use absolute paths for runner scripts and files")
    if args.llm_runtime == "local":
        wrapper = Path(args.llm_skill).expanduser().resolve().parent / "scripts/generate_acsl.py"
        if not wrapper.is_file():
            raise PipelineError("input", f"LOGOS wrapper not found: {wrapper}")
        runtime = wrapper.resolve().parent
        if runtime == output_dir or runtime in output_dir.parents or output_dir in runtime.parents:
            raise PipelineError("input", "LOGOS runtime files must be outside the output directory")
    else:
        if os.name != "posix":
            raise PipelineError("input", "Docker LLM mode requires POSIX host paths; use WSL on Windows")
        if shutil.which("docker") is None:
            raise PipelineError("input", "--llm-runtime docker requires Docker on the host PATH")
        if not args.llm_docker_image or args.llm_docker_image.startswith("-"):
            raise PipelineError("input", "--llm-docker-image must name a verifier image")
        for path in [output_dir, *(Path(value).expanduser().resolve() for value in args.include)]:
            validate_mount_path(path)


def wrapper_command(args, source, output_dir, contracts, annotated, evidence_file, options,
                    *, check_dependencies=False):
    wrapper_args = ["--check-dependencies"] if check_dependencies else [
                    str(source), "--contracts", str(contracts), "-o", str(annotated),
                    "--verify", "--verification-json", str(evidence_file),
                    *(f"--frama-c-option={value}" for value in options)]
    if args.llm_runtime == "local":
        wrapper = Path(args.llm_skill).expanduser().resolve().parent / "scripts/generate_acsl.py"
        return [sys.executable, str(wrapper), *wrapper_args], None
    name = f"autodeduct-logos-{uuid.uuid4().hex}"
    command = docker_run_options(args.llm_docker_platform, name)
    # Preserve absolute paths so verifier evidence matches the host task exactly.
    roots = {source.parent, *(Path(value).expanduser().resolve() for value in args.include)}
    for root in sorted(roots, key=str):
        validate_mount_path(root)
        if not root.is_dir():
            raise PipelineError("input", f"include/source directory does not exist: {root}")
        command += ["--mount", f"type=bind,source={root},target={root},readonly"]
    command += ["--mount", f"type=bind,source={output_dir},target={output_dir}",
                "--workdir", str(output_dir), args.llm_docker_image,
                "python3", "/opt/logos/skill/scripts/generate_acsl.py", *wrapper_args]
    return command, name


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
    if args.llm_runtime == "local":
        return _run_skill_workflow(args, source, output_dir, report,
                                   Path(args.llm_skill).expanduser().resolve())

    image_id = resolve_image(args.llm_docker_image, name="logos_image", report=report,
                             output_dir=output_dir, timeout=args.timeout)
    if image_id is None:
        return report
    pinned_args = copy.copy(args)
    pinned_args.llm_docker_image = image_id
    name = f"autodeduct-logos-{uuid.uuid4().hex}"
    extraction = run_container_stage(
        name="logos_skill", description="Extract the LOGOS skill from the pinned verifier image",
        command=[*docker_run_options(args.llm_docker_platform, name), image_id, "python3", "-c",
                 "from pathlib import Path; print(Path('/opt/logos/skill/SKILL.md').read_text(encoding='utf-8'), end='')"],
        container_name=name, report=report, cwd=output_dir, output_dir=output_dir,
        timeout=args.timeout,
    )
    report.stages.append(extraction)
    if extraction.status != "passed":
        report.errors.append({"stage": extraction.name, "message": extraction.error or "LOGOS skill extraction failed"})
        return report
    skill_text = Path(extraction.stdout_file).read_text(encoding="utf-8")
    if not skill_text.strip():
        extraction.status = "failed"
        extraction.error = "the verifier image contains an empty LOGOS SKILL.md"
        report.errors.append({"stage": extraction.name, "message": extraction.error})
        return report
    snapshot = output_dir / "llm-skill.md"
    output_info = output_dir.stat()
    output_identity = (output_info.st_dev, output_info.st_ino)
    extraction.artifact = str(snapshot)
    # Keep the instructions outside the agent workspace, and retain a review copy.
    with tempfile.TemporaryDirectory(prefix=".autodeduct-logos-skill-", dir=output_dir.parent) as cache:
        skill = Path(cache).resolve() / "SKILL.md"
        write_text(skill, skill_text)
        skill.chmod(0o400)
        try:
            return _run_skill_workflow(pinned_args, source, output_dir, report, skill)
        finally:
            write_text(snapshot, skill_text, expected_parent=output_identity)


def _run_skill_workflow(args, source, output_dir, report, skill):
    try:
        source_text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        report.errors.append({"stage": "llm_contracts", "message": str(error)})
        return report
    contracts = output_dir / "llm-contracts.json"
    annotated = output_dir / SAIDA_OUTPUT
    evidence_file = output_dir / "llm-verification.json"
    try:
        skill_text = skill.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        report.errors.append({"stage": "logos_skill", "message": f"could not read LOGOS skill: {error}"})
        return report
    skill_sha256 = hashlib.sha256(skill_text.encode("utf-8")).hexdigest()
    options = [*command_options(args, [source]), *args.wp_option]
    if args.wp_rte:
        options.append("-wp-rte")
    environment_command, environment_container = wrapper_command(
        args, source, output_dir, contracts, annotated, evidence_file, options,
        check_dependencies=True,
    )
    environment = run_container_stage(
        name="logos_environment", description=f"Check LOGOS verification dependencies ({args.llm_runtime})",
        command=environment_command, cwd=output_dir, output_dir=output_dir,
        timeout=args.timeout, container_name=environment_container, report=report,
    )
    report.stages.append(environment)
    if environment.status != "passed":
        report.errors.append({"stage": "environment", "message": environment.error or "LOGOS verification dependencies are unavailable"})
        return report
    command, container_name = wrapper_command(
        args, source, output_dir, contracts, annotated, evidence_file, options,
    )
    task_file = output_dir / "llm-task.json"
    write_text(task_file, json.dumps({
        "workflow": "generate-only",
        "skill_sha256": skill_sha256,
        "docker_image_id": args.llm_docker_image if args.llm_runtime == "docker" else None,
        "skill": str(skill), "source": str(source),
        "contracts": str(contracts), "annotated_source": str(annotated),
        "verification_json": str(evidence_file), "verification_options": options,
    }, indent=2) + "\n")
    prompt = (
        f"Use the skill at {json.dumps(str(skill))}. Read its complete SKILL.md and "
        f"follow its workflow on the task in {json.dumps(str(task_file))}. "
        "This is a generate-only task. Write the structured contracts JSON and stop. "
        "Author the structured contracts yourself following the skill; do not use a "
        "separate generator with built-in prompts. AutoDeduct will invoke the LOGOS "
        "Python wrapper for annotation and verification after you finish. Do not run "
        "the wrapper or Docker and do not write annotated source or verification JSON. "
        "Use exactly the supplied contract artifact "
        "paths. Preserve the original source and all existing specifications. Write "
        "only in the task output directory; do not modify the skill repository. "
        "If dependencies or permissions are unavailable, report the failure. "
        "Do not weaken the requested proof or substitute a different verifier."
    )
    runner = command_words(args.llm_runner)
    # Codex's automatic approval mode already selects workspace-write.
    sandbox = [] if "--approve-for-me" in runner else ["--sandbox", "workspace-write"]
    workflow = run_stage(
        name="llm_workflow", description="Generate contracts using the host Codex skill",
        command=[*runner, "--cd", str(output_dir),
                 "--skip-git-repo-check", *sandbox, "--json",
                 "--output-last-message", str(output_dir / "llm-final.txt"), prompt],
        cwd=output_dir, output_dir=output_dir, timeout=args.timeout, artifact=contracts,
    )
    report.stages.append(workflow)
    if workflow.status != "passed":
        report.errors.append({"stage": workflow.name, "message": workflow.error or "skill runner failed"})
        return report
    try:
        if skill.is_symlink() or hashlib.sha256(skill.read_text(encoding="utf-8").encode("utf-8")).hexdigest() != skill_sha256:
            raise ValueError("the LOGOS skill changed during generation")
        validate_contracts(contracts, source_text)
        if source.read_text(encoding="utf-8") != source_text:
            raise ValueError("skill changed the original input source")
        if output_dir.resolve() != output_dir or any(path.is_symlink() for path in (
            contracts, annotated, evidence_file, annotated.with_suffix(".wp-report.txt"),
            annotated.with_suffix(".wp-report.pdf"),
        )):
            raise ValueError("generated artifacts must be ordinary files in the output directory")
        if annotated.exists() or evidence_file.exists():
            raise ValueError("generate-only runner must not write annotated source or verifier evidence")
    except (OSError, ValueError) as error:
        report.errors.append({"stage": "llm_contracts", "message": str(error)})
        return report
    wrapper = run_container_stage(
        name="logos_verify", description=f"Annotate and verify with LOGOS ({args.llm_runtime})",
        command=command, cwd=output_dir, output_dir=output_dir,
        timeout=args.timeout, artifact=evidence_file,
        container_name=container_name, report=report,
    )
    report.stages.append(wrapper)
    if wrapper.status != "passed" and not evidence_file.is_file():
        report.errors.append({"stage": wrapper.name, "message": wrapper.error or "LOGOS wrapper failed"})
        return report
    verification = StageResult(
        name="skill_verify", description="Validate LOGOS WP evidence",
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
            write_text(path, evidence[stream])
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
    if wrapper.status != "passed" or report.errors:
        report.errors.append({"stage": wrapper.name, "message": wrapper.error or "LOGOS wrapper failed"})
        return report
    report.status = "passed"
    return report
