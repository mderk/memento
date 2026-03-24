from __future__ import annotations

import sys


def main() -> None:
    from scripts.infra.sandbox import apply_process_sandbox

    apply_process_sandbox([sys.executable, "-m", "scripts.cli", *sys.argv[1:]])

    from scripts.runner import main as runner_main

    runner_main()
