"""Build the shared Lambda archive from hash-locked wheels."""

import argparse
import csv
import io
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def archive_bytes(path: Path, members: set[str]) -> bytes:
    if path.name != "RECORD" or path.parent.suffix != ".dist-info":
        return path.read_bytes()
    # pip records scripts with a local interpreter shebang. Lambda omits those scripts.
    output = io.StringIO(newline="")
    with path.open(encoding="utf-8", newline="") as record:
        csv.writer(output).writerows(row for row in csv.reader(record) if row[0] in members)
    return output.getvalue().encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/forecast.zip")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as tmp:
        stage = Path(tmp)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--require-hashes",
                "--only-binary=:all:",
                "--no-compile",
                "--platform",
                "manylinux2014_aarch64",
                "--implementation",
                "cp",
                "--python-version",
                "3.12",
                "--target",
                str(stage),
                "-r",
                str(ROOT / "services/forecast/requirements.txt"),
            ],
            check=True,
        )
        pkg = stage / "services/forecast"
        pkg.mkdir(parents=True)
        shutil.copy(ROOT / "services/__init__.py", stage / "services")
        for source in (ROOT / "services/forecast").glob("*.py"):
            if source.name != "local.py":
                shutil.copy(source, pkg)
        shutil.copytree(
            ROOT / "services/observations",
            stage / "services/observations",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(
            ROOT / "services/pipeline",
            stage / "services/pipeline",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "operator*", "panel"),
        )
        shutil.copytree(
            ROOT / "services/passengers",
            stage / "services/passengers",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        grid = stage / "grid"
        grid.mkdir()
        for name in ("__init__.py", "source.py"):
            shutil.copy(ROOT / "grid" / name, grid / name)
        shutil.copytree(ROOT / "services/forecast/data", pkg / "data")
        temporary = args.output.with_suffix(".tmp")
        members = {
            path.relative_to(stage).as_posix()
            for path in stage.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and not path.is_relative_to(stage / "bin")
        }
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for name in sorted(members):
                info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                archive.writestr(
                    info, archive_bytes(stage / name, members), compress_type=ZIP_DEFLATED
                )
        temporary.replace(args.output)


if __name__ == "__main__":
    main()
