#!/usr/bin/env python3
"""GraphRAG and Documentation Link Verification Utility.

Validates that:
1. All file paths and links referenced in AGENTS.md exist on disk.
2. Symbols referenced in anchors exist within the referenced files.
3. All skill files under .agents/skills/ have valid YAML frontmatter and resolved links.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def strip_code_blocks(text: str) -> str:
    """Removes fenced and inline code blocks so code examples are not scanned as live links."""
    # Strip ``` ... ``` blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Strip `...` inline code blocks
    text = re.sub(r"`[^`\n]+`", "", text)
    return text


def check_agents_md(agents_md_path: Path) -> list[str]:
    errors = []
    if not agents_md_path.exists():
        return [f"AGENTS.md not found at {agents_md_path}"]

    raw_content = agents_md_path.read_text(encoding="utf-8")
    content = strip_code_blocks(raw_content)

    # Match markdown links: [text](path#anchor) or [text](path)
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    for match in link_pattern.finditer(content):
        anchor_text, target = match.groups()

        # Skip web urls or intra-page section links
        if target.startswith("http://") or target.startswith("https://") or target.startswith("#"):
            continue

        # Split path and anchor
        if "#" in target:
            file_part, line_anchor = target.split("#", 1)
        else:
            file_part, line_anchor = target, None

        target_file = (REPO_ROOT / file_part).resolve()
        if not target_file.exists():
            errors.append(f"Broken file link: [{anchor_text}]({target}) -> File not found: {file_part}")
            continue

        if line_anchor and line_anchor.startswith("L"):
            # Check line numbers e.g. L70 or L70-L202
            m = re.match(r"^L(\d+)(?:-L(\d+))?$", line_anchor)
            if m:
                start_line = int(m.group(1))
                end_line = int(m.group(2)) if m.group(2) else start_line
                file_lines = target_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                total_lines = len(file_lines)

                if start_line > total_lines:
                    errors.append(
                        f"Line out of range in [{anchor_text}]({target}): start line {start_line} > total lines {total_lines}"
                    )
                else:
                    # If anchor_text is a file reference (e.g. cli.py), don't treat it as a symbol
                    if re.search(r"\.(py|md|json|txt|toml)$", anchor_text.strip("`()")):
                        continue

                    # If anchor_text looks like a Python symbol identifier (e.g. Class.method or function)
                    clean_sym = anchor_text.strip("`()")
                    symbols_to_check = clean_sym.split(".") if "." in clean_sym else [clean_sym]
                    for sym in symbols_to_check:
                        if sym.isidentifier():
                            window_start = max(0, start_line - 15)
                            window_end = min(total_lines, end_line + 15)
                            window_text = "\n".join(file_lines[window_start:window_end])
                            if sym not in window_text:
                                if not any(sym in line for line in file_lines):
                                    errors.append(
                                        f"Symbol '{sym}' referenced in [{anchor_text}]({target}) not found in {file_part}"
                                    )

    return errors


def check_skills_dir(skills_dir: Path) -> list[str]:
    errors = []
    if not skills_dir.exists():
        return [f"Skills directory not found at {skills_dir}"]

    skill_files = sorted(list(skills_dir.glob("*/SKILL.md")))
    if not skill_files:
        return [f"No SKILL.md files found in {skills_dir}"]

    for skill_file in skill_files:
        raw_content = skill_file.read_text(encoding="utf-8")
        # Check YAML frontmatter
        fm_match = re.match(r"^---\n(.*?)\n---\n", raw_content, re.DOTALL)
        if not fm_match:
            errors.append(f"Missing YAML frontmatter in {skill_file.relative_to(REPO_ROOT)}")
            continue

        frontmatter = fm_match.group(1)
        if "name:" not in frontmatter:
            errors.append(f"Missing 'name:' in frontmatter of {skill_file.relative_to(REPO_ROOT)}")
        if "description:" not in frontmatter:
            errors.append(f"Missing 'description:' in frontmatter of {skill_file.relative_to(REPO_ROOT)}")

        # Check relative links outside code blocks
        body = strip_code_blocks(raw_content[fm_match.end() :])
        link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        for match in link_pattern.finditer(body):
            anchor_text, target = match.groups()
            if target.startswith("http://") or target.startswith("https://") or target.startswith("#"):
                continue

            file_part = target.split("#", 1)[0]
            target_path = (skill_file.parent / file_part).resolve()
            if not target_path.exists():
                errors.append(
                    f"Broken link in {skill_file.relative_to(REPO_ROOT)}: [{anchor_text}]({target}) -> File not found"
                )

    return errors


def check_intents_json(intents_path: Path) -> tuple[list[str], int]:
    errors = []
    if not intents_path.exists():
        return [f"intents.json not found at {intents_path}"], 0

    try:
        data = json.loads(intents_path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"Malformed JSON in {intents_path}: {e}"], 0

    intents = data.get("intents", [])
    if not isinstance(intents, list):
        return [f"Field 'intents' must be a list in {intents_path}"], 0

    required_keys = {"id", "type", "subject", "predicate", "object", "source_file", "line_anchor", "description"}
    count = 0

    for idx, intent in enumerate(intents):
        count += 1
        intent_id = intent.get("id", f"index_{idx}")
        missing_keys = required_keys - set(intent.keys())
        if missing_keys:
            errors.append(
                f"Intent '{intent_id}' in {intents_path.name} is missing required fields: {sorted(missing_keys)}"
            )
            continue

        src_file_rel = intent["source_file"]
        target_file = (REPO_ROOT / src_file_rel).resolve()
        if not target_file.exists():
            errors.append(f"Intent '{intent_id}' references non-existent file: {src_file_rel}")
            continue

        file_lines = target_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        total_lines = len(file_lines)

        line_anchor = intent.get("line_anchor", "")
        if line_anchor.startswith("L"):
            m = re.match(r"^L(\d+)(?:-L(\d+))?$", line_anchor)
            if m:
                start_line = int(m.group(1))
                if start_line > total_lines:
                    errors.append(
                        f"Intent '{intent_id}' line out of range in {src_file_rel}: start line {start_line} > total lines {total_lines}"
                    )

        symbol = intent.get("symbol")
        if symbol:
            clean_sym = symbol.strip("`()")
            sym_parts = clean_sym.split(".") if "." in clean_sym else [clean_sym]
            target_sym = sym_parts[-1]
            if target_sym.isidentifier() and not any(target_sym in line for line in file_lines):
                errors.append(f"Intent '{intent_id}' references symbol '{symbol}' not found in {src_file_rel}")

    return errors, count


def check_unknowns_json(unknowns_path: Path) -> tuple[list[str], int]:
    errors = []
    if not unknowns_path.exists():
        return [], 0  # Optional file

    try:
        data = json.loads(unknowns_path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"Malformed JSON in {unknowns_path}: {e}"], 0

    unknowns = data.get("unknowns", [])
    if not isinstance(unknowns, list):
        return [f"Field 'unknowns' must be a list in {unknowns_path}"], 0

    required_keys = {
        "id",
        "symbol",
        "source_file",
        "line_anchor",
        "category",
        "description",
        "impact",
        "recommendation",
    }
    count = 0

    for idx, item in enumerate(unknowns):
        count += 1
        item_id = item.get("id", f"index_{idx}")
        missing_keys = required_keys - set(item.keys())
        if missing_keys:
            errors.append(
                f"Unknown '{item_id}' in {unknowns_path.name} is missing required fields: {sorted(missing_keys)}"
            )
            continue

        src_file_rel = item["source_file"]
        target_file = (REPO_ROOT / src_file_rel).resolve()
        if not target_file.exists():
            errors.append(f"Unknown '{item_id}' references non-existent file: {src_file_rel}")
            continue

        file_lines = target_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        total_lines = len(file_lines)

        line_anchor = item.get("line_anchor", "")
        if line_anchor.startswith("L"):
            m = re.match(r"^L(\d+)(?:-L(\d+))?$", line_anchor)
            if m:
                start_line = int(m.group(1))
                if start_line > total_lines:
                    errors.append(
                        f"Unknown '{item_id}' line out of range in {src_file_rel}: start line {start_line} > total lines {total_lines}"
                    )

        symbol = item.get("symbol")
        if symbol:
            clean_sym = symbol.strip("`()")
            sym_parts = clean_sym.split(".") if "." in clean_sym else [clean_sym]
            target_sym = sym_parts[-1]
            if target_sym.isidentifier() and not any(target_sym in line for line in file_lines):
                errors.append(f"Unknown '{item_id}' references symbol '{symbol}' not found in {src_file_rel}")

    return errors, count


def main() -> int:
    print("=" * 60)
    print("Coddy GraphRAG & Intent Link Verification")
    print("=" * 60)

    agents_md = REPO_ROOT / "AGENTS.md"
    skills_dir = REPO_ROOT / ".agents" / "skills"
    intents_json = REPO_ROOT / "docs" / "intents.json"
    unknowns_json = REPO_ROOT / "docs" / "unknowns.json"

    agents_errors = check_agents_md(agents_md)
    skills_errors = check_skills_dir(skills_dir)
    intents_errors, intent_count = check_intents_json(intents_json)
    unknowns_errors, unknowns_count = check_unknowns_json(unknowns_json)

    all_errors = agents_errors + skills_errors + intents_errors + unknowns_errors

    if all_errors:
        print("\n❌ Verification Failed! Discrepancies detected:")
        for err in all_errors:
            print(f"  - {err}")
        print("\nPlease fix the above broken references and re-run.")
        return 1

    print("\n✅ Verification Passed!")
    print("  - AGENTS.md: All file paths, symbols, and line anchors verified.")
    print(
        f"  - Skills: All {len(list(skills_dir.glob('*/SKILL.md')))} SKILL.md files validated with correct frontmatter and links."
    )
    print(
        f"  - Intents JSON: All {intent_count} intents in docs/intents.json verified against codebase symbols and line anchors."
    )
    if unknowns_count > 0:
        print(
            f"  - Unknowns JSON: All {unknowns_count} items in docs/unknowns.json verified against codebase symbols and line anchors."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
