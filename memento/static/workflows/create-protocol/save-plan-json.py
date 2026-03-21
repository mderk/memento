"""Save plan JSON from stdin to protocol_dir/plan.json."""

import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: save-plan-json.py <protocol_dir>"}))
        sys.exit(1)

    protocol_dir = Path(sys.argv[1])
    plan_json = protocol_dir / "plan.json"

    data = sys.stdin.read().strip()
    if not data:
        print(json.dumps({"error": "No plan data on stdin"}))
        sys.exit(1)

    # Validate JSON
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    # Pretty-print to file
    plan_json.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"saved": str(plan_json), "keys": len(parsed)}))


if __name__ == "__main__":
    main()
