from pathlib import Path
import re


MUTABLE_ACTION_REF = re.compile(
    r"^\s*-?\s*uses:\s*actions/[^@\s]+@(?![0-9a-fA-F]{40}(?:\s|$))[^\s#]+",
    re.MULTILINE,
)


def test_github_actions_are_pinned_to_full_commit_shas() -> None:
    workflow_root = Path(".github/workflows")
    offenders: list[str] = []
    for path in sorted(workflow_root.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        for match in MUTABLE_ACTION_REF.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path}:{line_no}: {match.group(0).strip()}")
    assert not offenders, "GitHub Actions must use immutable 40-character commit SHAs:\n" + "\n".join(offenders)
