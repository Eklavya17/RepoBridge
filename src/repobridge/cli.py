"""`repobridge` command-line entry point. Subcommands (index, query, bundle, run) arrive
in Stages A-C."""

import argparse

from repobridge import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repobridge")
    parser.add_argument("--version", action="version", version=f"repobridge {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
