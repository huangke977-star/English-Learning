"""Build learner-facing PDFs and page indexes from the course Markdown files.

The source Markdown remains authoritative.  This script deliberately keeps the
renderer small and deterministic so it can be rerun after content changes.
Review records and templates are not included in learner PDFs; Book9's tests
and answers are included because they are learner-facing material.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


COURSE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = COURSE_DIR / "output" / "pdf"
TMP_DIR = COURSE_DIR.parent / "tmp" / "pdfs"
TODAY = date.today().isoformat()
PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT = RIGHT = 18 * mm
TOP = 18 * mm
BOTTOM = 17 * mm
CONTENT_WIDTH = PAGE_WIDTH - LEFT - RIGHT


def register_fonts() -> tuple[str, str, str]:
    """Register a Windows font with broad Chinese and Latin coverage."""

    candidates = [
        (Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf"), "NotoSansSC"),
        (Path(r"C:\Windows\Fonts\Deng.ttf"), "Deng"),
    ]
    regular = None
    for path, name in candidates:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
                regular = name
                break
            except Exception:
                continue
    if regular is None:
        regular = "Helvetica"

    bold_path = Path(r"C:\Windows\Fonts\Dengb.ttf")
    bold = regular
    if bold_path.exists() and regular != "Helvetica":
        try:
            pdfmetrics.registerFont(TTFont("DengBold", str(bold_path)))
            bold = "DengBold"
        except Exception:
            pass
    ipa_path = Path(r"C:\Windows\Fonts\DejaVuSansMono_0.ttf")
    ipa = regular
    if ipa_path.exists():
        try:
            pdfmetrics.registerFont(TTFont("DejaVuIPA", str(ipa_path)))
            ipa = "DejaVuIPA"
        except Exception:
            pass
    return regular, bold, ipa


FONT, FONT_BOLD, FONT_IPA = register_fonts()


def normalize_text(text: str) -> str:
    """Remove Markdown decoration while retaining readable source text."""

    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = text.replace("~~", "")
    text = text.replace("`", "")
    escaped = html.escape(text, quote=False)
    # Windows' Chinese fonts do not contain the full IPA block.  Apply a
    # narrow fallback only to phonetic symbols so Chinese text keeps its
    # consistent primary typeface.
    if FONT_IPA != FONT:
        escaped = re.sub(
            r"([\u0250-\u02af\u02c0-\u02ff\u1d00-\u1d7f])",
            rf'<font name="{FONT_IPA}">\1</font>',
            escaped,
        )
    return escaped


def first_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            return re.sub(r"[`*_]", "", match.group(1))
    return path.stem


def split_table_line(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    return [part.strip() for part in value.split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_line(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


@dataclass
class Styles:
    title: ParagraphStyle
    h1: ParagraphStyle
    h2: ParagraphStyle
    h3: ParagraphStyle
    body: ParagraphStyle
    quote: ParagraphStyle
    bullet: ParagraphStyle
    code: ParagraphStyle
    table: ParagraphStyle
    table_header: ParagraphStyle
    small: ParagraphStyle


def make_styles() -> Styles:
    base = dict(fontName=FONT, textColor=colors.HexColor("#243247"), wordWrap="CJK")
    return Styles(
        title=ParagraphStyle("CourseTitle", parent=None, fontName=FONT_BOLD, fontSize=25, leading=32, alignment=TA_CENTER, textColor=colors.HexColor("#16324F"), spaceAfter=10),
        h1=ParagraphStyle("H1", parent=None, fontName=FONT_BOLD, fontSize=18, leading=23, textColor=colors.HexColor("#16324F"), spaceBefore=10, spaceAfter=8, keepWithNext=True, wordWrap="CJK"),
        h2=ParagraphStyle("H2", parent=None, fontName=FONT_BOLD, fontSize=13.5, leading=18, textColor=colors.HexColor("#1D5D78"), spaceBefore=9, spaceAfter=5, keepWithNext=True, wordWrap="CJK"),
        h3=ParagraphStyle("H3", parent=None, fontName=FONT_BOLD, fontSize=11, leading=15, textColor=colors.HexColor("#3A6B78"), spaceBefore=7, spaceAfter=4, keepWithNext=True, wordWrap="CJK"),
        body=ParagraphStyle("Body", parent=None, fontSize=9.4, leading=14, spaceAfter=6, **base),
        quote=ParagraphStyle("Quote", parent=None, fontSize=8.8, leading=13, leftIndent=9, borderPadding=5, borderColor=colors.HexColor("#A9C9D5"), borderWidth=0.7, borderLeft=True, spaceAfter=6, **{**base, "textColor": colors.HexColor("#486273")}),
        bullet=ParagraphStyle("Bullet", parent=None, fontSize=9.2, leading=13.5, leftIndent=13, firstLineIndent=-8, spaceAfter=3, **base),
        code=ParagraphStyle("Code", parent=None, fontName="Courier", fontSize=7.7, leading=10.5, backColor=colors.HexColor("#F2F5F7"), borderPadding=5, spaceAfter=7, wordWrap="CJK"),
        table=ParagraphStyle("Table", parent=None, fontSize=7.5, leading=10, **base),
        table_header=ParagraphStyle("TableHeader", parent=None, fontSize=7.5, leading=10, **{**base, "fontName": FONT_BOLD, "textColor": colors.white}),
        small=ParagraphStyle("Small", parent=None, fontSize=8, leading=11, alignment=TA_CENTER, **{**base, "textColor": colors.HexColor("#607284")}),
    )


STYLES = make_styles()


class FileStart(Flowable):
    """Zero-size marker used to collect the first page of each source file."""

    def __init__(self, key: str):
        super().__init__()
        self._file_key = key
        self.width = 0
        self.height = 0

    def draw(self) -> None:
        return None


class CourseDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, document_title: str):
        super().__init__(filename, pagesize=A4, leftMargin=LEFT, rightMargin=RIGHT, topMargin=TOP, bottomMargin=BOTTOM, title=document_title, author="English Learning Project")
        frame = Frame(LEFT, BOTTOM, CONTENT_WIDTH, PAGE_HEIGHT - TOP - BOTTOM, id="normal", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="course", frames=[frame], onPage=self._draw_page)])
        self.page_map: dict[str, int] = {}

    def afterFlowable(self, flowable: Flowable) -> None:
        key = getattr(flowable, "_file_key", None)
        if key and key not in self.page_map:
            self.page_map[key] = self.page

    def _draw_page(self, canvas, doc) -> None:
        canvas.saveState()
        if doc.page > 1:
            canvas.setStrokeColor(colors.HexColor("#D7E1E7"))
            canvas.setLineWidth(0.5)
            canvas.line(LEFT, PAGE_HEIGHT - 11 * mm, PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 11 * mm)
            canvas.setFont(FONT, 7.5)
            canvas.setFillColor(colors.HexColor("#71808C"))
            canvas.drawString(LEFT, PAGE_HEIGHT - 8.5 * mm, "American English Integrated Course")
        canvas.setStrokeColor(colors.HexColor("#D7E1E7"))
        canvas.setLineWidth(0.5)
        canvas.line(LEFT, 10 * mm, PAGE_WIDTH - RIGHT, 10 * mm)
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor("#71808C"))
        canvas.drawCentredString(PAGE_WIDTH / 2, 6.5 * mm, str(doc.page))
        canvas.restoreState()


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(normalize_text(text), style)


def markdown_flowables(path: Path, key: str) -> list[Flowable]:
    lines = path.read_text(encoding="utf-8").splitlines()
    result: list[Flowable] = [FileStart(key), paragraph(first_heading(path), STYLES.h1)]
    i = 0
    in_code = False
    code_lines: list[str] = []
    while i < len(lines):
        raw = lines[i].rstrip()
        stripped = raw.strip()
        if stripped.startswith("```"):
            if in_code:
                # The code block is already escaped; do not pass it through
                # paragraph(), which would escape ampersands a second time.
                result.append(Paragraph("<br/>".join(normalize_text(x) for x in code_lines), STYLES.code))
                code_lines = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(raw)
            i += 1
            continue
        if not stripped:
            i += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)), 3)
            style = (STYLES.h1, STYLES.h2, STYLES.h3)[level - 1]
            # The first heading was emitted above; avoid duplicating it.
            if not (len(result) == 2 and level == 1):
                result.append(paragraph(heading.group(2), style))
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            rows = [split_table_line(stripped)]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_table_line(lines[i]))
                i += 1
            max_cols = max(len(row) for row in rows)
            data = []
            for row_index, row in enumerate(rows):
                row = row + [""] * (max_cols - len(row))
                style = STYLES.table_header if row_index == 0 else STYLES.table
                data.append([paragraph(cell, style) for cell in row])
            col_width = CONTENT_WIDTH / max_cols
            table = Table(data, colWidths=[col_width] * max_cols, repeatRows=1, hAlign="LEFT", splitByRow=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6F86")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7C9D1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8FA")]),
            ]))
            result.extend([Spacer(1, 3), table, Spacer(1, 6)])
            continue
        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"): 
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[i].strip()))
                i += 1
            result.append(paragraph(" ".join(quote_lines), STYLES.quote))
            continue
        bullet_match = re.match(r"^[-*+]\s+(.+)$", stripped)
        numbered_match = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if bullet_match or numbered_match:
            marker = "•" if bullet_match else "1."
            result.append(paragraph(f"{marker} {bullet_match.group(1) if bullet_match else numbered_match.group(1)}", STYLES.bullet))
            i += 1
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            result.append(Spacer(1, 5))
            i += 1
            continue
        paragraph_lines = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or re.match(r"^(#{1,6})\s+", nxt) or nxt.startswith((">", "|", "```")) or re.match(r"^[-*+]\s+", nxt) or re.match(r"^\d+[.)]\s+", nxt):
                break
            paragraph_lines.append(nxt)
            i += 1
        result.append(paragraph(" ".join(paragraph_lines), STYLES.body))
    return result


def learner_files() -> list[Path]:
    files = [COURSE_DIR / name for name in ("README.md", "ROADMAP.md", "STUDY-ROUTES.md") if (COURSE_DIR / name).exists()]
    for directory in sorted(COURSE_DIR.glob("[0-9][0-9]-*")):
        if not directory.is_dir():
            continue
        files.extend(
            sorted(
                (path for path in directory.glob("*.md") if not (directory.name == "09-Reviews-and-Answers" and path.name == "README.md")),
                key=lambda p: p.name.lower(),
            )
        )
    return files


def book_files(book_number: int) -> list[Path]:
    directory = next(COURSE_DIR.glob(f"{book_number:02d}-*"))
    return sorted(
        (path for path in directory.glob("*.md") if not (book_number == 9 and path.name == "README.md")),
        key=lambda p: p.name.lower(),
    )


def build_pdf(output_path: Path, files: Iterable[Path], title: str, cover_subtitle: str) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = CourseDocTemplate(str(output_path), title)
    story: list[Flowable] = [
        Spacer(1, 39 * mm),
        paragraph(title, STYLES.title),
        paragraph(cover_subtitle, ParagraphStyle("CoverSub", parent=STYLES.body, alignment=TA_CENTER, fontSize=12, leading=18, textColor=colors.HexColor("#426779"))),
        Spacer(1, 10 * mm),
        paragraph(f"版本 v1.0 · 生成日期 {TODAY}", STYLES.small),
        Spacer(1, 25 * mm),
        paragraph("本 PDF 由项目 Markdown 源文件自动排版生成。正文、例句、练习和答案以仓库中的文字教材为准；PDF 页码仅对本版本有效。", STYLES.quote),
        PageBreak(),
    ]
    for index, path in enumerate(files):
        if index:
            story.append(PageBreak())
        key = str(path.relative_to(COURSE_DIR)).replace("\\", "/")
        story.extend(markdown_flowables(path, key))
    doc.multiBuild(story)
    return doc.page_map


def write_index(path: Path, title: str, pdf_name: str, page_map: dict[str, int], files: Iterable[Path]) -> None:
    lines = [
        f"# {title} 页面索引",
        "",
        f"对应 PDF：`{pdf_name}`",
        "",
        f"> 生成日期：{TODAY}。页码以当前 PDF v1.0 为准；重新排版后请重新生成本索引。",
        "",
        "| 源文件 | 首页 | 内容标题 |",
        "| --- | ---: | --- |",
    ]
    for source in files:
        key = str(source.relative_to(COURSE_DIR)).replace("\\", "/")
        lines.append(f"| `{key}` | {page_map.get(key, '-')} | {first_heading(source)} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    all_files = learner_files()
    combined_pdf = OUTPUT_DIR / "complete-course.pdf"
    combined_map = build_pdf(combined_pdf, all_files, "美式英语综合能力训练教材", "American English Integrated Course · Book0-Book9")
    write_index(COURSE_DIR / "indexes" / "page-index.md", "整套教材", combined_pdf.name, combined_map, all_files)

    for number in range(10):
        files = book_files(number)
        pdf_path = OUTPUT_DIR / f"book{number}.pdf"
        page_map = build_pdf(pdf_path, files, f"Book{number} · 美式英语综合能力训练", f"American English Integrated Course · Book{number}")
        write_index(OUTPUT_DIR / f"book{number}-page-index.md", f"Book{number}", pdf_path.name, page_map, files)

    manifest = OUTPUT_DIR / "README.md"
    manifest.write_text(
        "# PDF 发布包\n\n"
        f"生成日期：{TODAY}\n\n"
        "本目录包含整套教材和 Book0-Book9 分册 PDF。整套页面索引位于 `../../indexes/page-index.md`；分册索引与对应 PDF 放在本目录。\n\n"
        "PDF 由 `tools/build_pdfs.py` 从 Markdown 自动生成。源文件更新后，请重新运行脚本并复核渲染页面。\n",
        encoding="utf-8",
    )
    print(f"Built {len(all_files)} source files into {combined_pdf}")
    print(f"Combined pages: {max(combined_map.values(), default=1)}")


if __name__ == "__main__":
    main()
