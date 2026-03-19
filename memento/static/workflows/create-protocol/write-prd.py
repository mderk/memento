# ruff: noqa: T201
"""Write prd.md from structured PRD JSON (passed via PRD_JSON env var)."""

import json
import os
import sys
from datetime import date
from pathlib import Path


def main() -> None:
    protocol_dir = Path(sys.argv[1])
    protocol_dir.mkdir(parents=True, exist_ok=True)

    prd_path = protocol_dir / "prd.md"
    if prd_path.is_file():
        print(json.dumps({"skipped": True, "reason": "prd.md already exists"}))
        return

    prd_json = os.environ.get("PRD_JSON", "")
    if not prd_json:
        print(json.dumps({"error": "PRD_JSON not set"}))
        sys.exit(1)

    prd = json.loads(prd_json)
    today = date.today().isoformat()

    lines = [
        f"# {prd['title']} — Requirements",
        "",
        "## Problem Statement",
        "",
        prd["problem_statement"],
        "",
        "## Requirements",
        "",
    ]
    for req in prd.get("requirements", []):
        lines.append(f"- {req}")

    lines.extend(["", "## Constraints", ""])
    for c in prd.get("constraints", []):
        lines.append(f"- {c}")

    lines.extend(["", "## Acceptance Criteria", ""])
    for ac in prd.get("acceptance_criteria", []):
        lines.append(f"- {ac}")

    lines.extend(["", "## Source", "", f"Generated from task description: {today}", ""])

    prd_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"created": str(prd_path)}))


if __name__ == "__main__":
    main()
