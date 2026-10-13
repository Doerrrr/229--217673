"""Pack just the first answer source and notes, not inputs or generated results."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import stat
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    app = root / "environment/app"
    paths = sorted(app.rglob("*.py"))
    assert app / "lineage.py" in paths, "Missing environment/app/lineage.py"
    assert root / "answer_notes.md" != args.out.resolve()
    assert (root / "answer_notes.md").is_file(), "Complete answer_notes.md first"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("xb") as stream, zipfile.ZipFile(stream, "w") as archive:
        for path in paths + [root / "answer_notes.md"]:
            assert not path.is_symlink(), "Symlinks are not accepted"
            body = path.read_bytes()
            assert len(body) <= 4_000_000
            name = "app/" + path.relative_to(app).as_posix() if path in paths else "answer_notes.md"
            info = zipfile.ZipInfo(name, (2026, 10, 13, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, body)
    print("answer_sha256=" + hashlib.sha256(args.out.read_bytes()).hexdigest())
    print(str(args.out.resolve()))


if __name__ == "__main__":
    main()
