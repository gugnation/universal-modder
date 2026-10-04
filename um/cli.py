"""`um` command line: one entry point for every tool, so skills can say `um <group> <cmd>`."""
from __future__ import annotations

import argparse
import importlib
import sys

from um import __doc__ as DOC, __version__

GROUPS = ["scan", "fal", "sprite", "render3d", "video", "win", "backup", "publish", "llm"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="um", description=DOC, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"universal-modder {__version__}")
    sub = ap.add_subparsers(dest="group", metavar="<group>")
    for g in GROUPS:
        importlib.import_module(f"um.{g}").register(sub)
    argv = sys.argv[1:] if argv is None else list(argv)
    # everything after a bare `--` is handed to the command untouched (e.g. extra llama-server flags)
    rest = argv[argv.index("--") + 1:] if "--" in argv else []
    args = ap.parse_args(argv[:len(argv) - len(rest) - 1] if "--" in argv else argv)
    args.passthrough = rest
    if not getattr(args, "func", None):
        # a group without a command: show that group's help
        if args.group:
            ap.parse_args([args.group, "--help"])
        ap.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
