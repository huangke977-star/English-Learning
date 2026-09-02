"""Fill learner-navigation PDF page placeholders from indexes/page-index.md."""

from pathlib import Path
import re


COURSE_DIR = Path(__file__).resolve().parents[1]
INDEX = COURSE_DIR / "indexes" / "page-index.md"
PLACEHOLDER = "PDF 参考页码：发布后填写。"


def main() -> None:
    page_map: dict[str, int] = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\| `([^`]+)` \| (\d+) \|", line)
        if match:
            page_map[match.group(1)] = int(match.group(2))

    changed = 0
    for directory in sorted(COURSE_DIR.glob("[0-9][0-9]-*")):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if PLACEHOLDER not in text:
                continue
            key = path.relative_to(COURSE_DIR).as_posix()
            page = page_map.get(key)
            if page is None:
                raise SystemExit(f"No page-index entry for {key}")
            updated = text.replace(PLACEHOLDER, f"PDF 参考页码：整套教材 v1.0，第 {page} 页。")
            path.write_text(updated, encoding="utf-8")
            changed += 1
    print(f"Updated {changed} source files")


if __name__ == "__main__":
    main()
