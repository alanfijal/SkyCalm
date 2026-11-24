"""Build the read-only forecast Lambda archive from hash-locked wheels."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


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
        shutil.copytree(ROOT / "services/forecast/data", pkg / "data")
        temporary = args.output.with_suffix(".tmp")
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                rel = path.relative_to(stage)
                if not path.is_file() or "__pycache__" in rel.parts or rel.parts[0] == "bin":
                    continue
                info = ZipInfo(rel.as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED)
        temporary.replace(args.output)


if __name__ == "__main__":
    main()
