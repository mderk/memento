"""Entry point: python -m dashboard [--cwd DIR] [--port PORT] [--no-open]

Starts the dashboard web server. Defaults to auto port selection.
"""

import argparse

from .cli import cmd_serve


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dashboard",
        description="Workflow dashboard server",
    )
    parser.add_argument("--cwd", default=".", help="Project directory")
    parser.add_argument("--port", type=int, default=0, help="Port (0 = auto)")
    parser.add_argument("--host", default="127.0.0.1", help="Host")
    parser.add_argument("--no-open", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    cmd_serve(args.cwd, args.host, args.port, not args.no_open)


if __name__ == "__main__":
    main()
