import argparse
from pathlib import Path

from .transfer import MemoryTransfer


def main() -> None:
    parser = argparse.ArgumentParser(prog="memory-portability")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("recover")
    restore = commands.add_parser("import")
    restore.add_argument("--transfer-dir", type=Path)
    restore.add_argument("--filename", required=True)
    restore.add_argument("--mode", choices=("overwrite", "append"), default="overwrite")
    restore.add_argument("--no-history", action="store_true")
    restore.add_argument("--no-vector", action="store_true")
    args = parser.parse_args()
    transfer = MemoryTransfer(getattr(args, "transfer_dir", None))
    if args.command == "recover":
        transfer.recover()
    else:
        transfer.import_archive(
            args.filename,
            args.mode,
            not args.no_history,
            not args.no_vector,
        )


if __name__ == "__main__":
    main()
