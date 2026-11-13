from pathlib import Path


# FIXME: throw exception if doesn't exists
def load_instructions(instruction_path: Path | None = None) -> str:
    """Loads instructions from INSTRUCTIONS.md."""
    path = instruction_path or (Path(__file__).parent / "INSTRUCTIONS.md")
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "Build a research plan for the user request."
