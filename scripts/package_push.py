"""Package the lockfile-installed production modules with deterministic metadata."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/push.zip")
    out = parser.parse_args().output
    src = ROOT / "services/delivery"
    modules = src / "node_modules"
    if not (modules / "web-push/src/index.js").is_file():
        raise SystemExit("Run npm ci --omit=dev --ignore-scripts in services/delivery first.")
    paths = [
        src / "index.mjs",
        src / "package.json",
        *(
            p
            for p in modules.rglob("*")
            if p.is_file()
            and not p.is_symlink()
            and ".bin" not in p.parts
            and p.name != ".package-lock.json"
        ),
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with ZipFile(tmp, "w") as z:
        for p in sorted(paths):
            entry = ZipInfo(p.relative_to(src).as_posix(), (2020, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100644 << 16
            z.writestr(entry, p.read_bytes(), compress_type=ZIP_DEFLATED)
    tmp.replace(out)


if __name__ == "__main__":
    main()
