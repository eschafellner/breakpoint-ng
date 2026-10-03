"""Back up and restore the mounted media directory without Django or a server."""

import argparse
import gzip
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile


def regular_files_only(member):
    if not (member.isfile() or member.isdir()):
        raise ValueError("Medien-Backup enthält Links oder Spezialdateien")
    return member


def backup(root, output):
    if not root.is_dir():
        raise ValueError("Medien-Verzeichnis fehlt")
    with tarfile.open(fileobj=output, mode="w|gz") as archive:
        archive.add(root, arcname="media", filter=regular_files_only)


def restore(root, source, validate_only=False):
    # Verify the entire gzip stream before extracting any bytes, including CRC.
    with tempfile.TemporaryFile() as uncompressed:
        with gzip.GzipFile(fileobj=source, mode="rb") as compressed:
            shutil.copyfileobj(compressed, uncompressed)
        uncompressed.seek(0)
        with tarfile.open(fileobj=uncompressed, mode="r:") as archive:
            members = archive.getmembers()
            if not members:
                raise ValueError("Leeres Medien-Archiv")
            root = root.resolve()
            for member in members:
                path = PurePosixPath(member.name)
                if (
                    path.is_absolute()
                    or not path.parts
                    or path.parts[0] != "media"
                    or ".." in path.parts
                    or "\\" in member.name
                    or ":" in member.name
                    or not (member.isfile() or member.isdir())
                    or not (root.parent / member.name).resolve().is_relative_to(root)
                ):
                    raise ValueError("Ungültiger Eintrag im Medien-Archiv")
            if not validate_only:
                root.mkdir(parents=True, exist_ok=True)
                archive.extractall(root.parent, members=members, filter="data")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["backup", "validate", "restore"])
    parser.add_argument("--root", type=Path, default=Path("/app/media"))
    args = parser.parse_args()
    if args.mode == "backup":
        backup(args.root, sys.stdout.buffer)
    else:
        restore(args.root, sys.stdin.buffer, validate_only=args.mode == "validate")


if __name__ == "__main__":
    try:
        main()
    except (OSError, EOFError, ValueError, tarfile.TarError) as error:
        print(f"Medien-Archiv fehlgeschlagen: {error}", file=sys.stderr)
        sys.exit(1)
