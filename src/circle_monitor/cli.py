from __future__ import annotations

import argparse

from circle_monitor.app import create_application


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Circle monitoring bot")
    parser.add_argument("--config", default="config.toml", help="Path to TOML config file")
    parser.add_argument("--once", action="store_true", help="Run a single polling cycle")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_application(args.config)
    if args.once:
        app.run_once()
    else:
        app.run_forever()


if __name__ == "__main__":
    main()
