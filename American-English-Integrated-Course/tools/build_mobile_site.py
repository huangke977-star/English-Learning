"""Generate a mobile-first static study site from the course Markdown.

The source Markdown stays authoritative. This dependency-free generator builds
a responsive PWA under mobile/ with phase navigation, unit pages, progress
stored in localStorage, and on-demand audio players.
"""

from __future__ import annotations

import html
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "mobile"
ASSETS = SITE / "assets"
UNITS_DIR = SITE / "units"
BOOKS_DIR = SITE / "books"
INLINE_AUDIO_DIR = ROOT / "assets" / "audio" / "inline"
INLINE_AUDIO_TEXTS: set[str] = set()

BOOKS = {
    0: ("学习指南与能力诊断", "确定起点，建立每日学习与复习习惯。"),
    1: ("美式英语发音基础", "从 IPA、元音与辅音开始，建立可重复的发音方法。"),
    2: ("听力与自然语流", "练习意群、重音、弱读、连读和听写。"),
    3: ("实用语法与句子构造", "用准确句型表达时间、条件、原因和请求。"),
    4: ("核心词汇、搭配与短语动词", "在日常、工作和服务场景中积累可直接使用的表达。"),
    5: ("高频口语句型", "完成问候、请求、澄清、协商与工作交流。"),
    6: ("分级阅读训练", "从短句到邮件、简报和观点文章建立阅读策略。"),
    7: ("英语写作训练", "从句子准确性逐步写到邮件、叙事与工作说明。"),
    8: ("真实场景综合任务", "把听、说、读、写组合到餐厅、旅行、工作和社交任务中。"),
    9: ("复习、测试与答案", "定位薄弱点，完成综合测试并建立错误档案。"),
}

PHASES = (
    ("phase-1", "Phase 1", "学习方法与发音基础", "先建立学习循环，再开始听辨和发音。", (0, 1)),
    ("phase-2", "Phase 2", "语流与听辨", "让句子不再是逐词拼接，而是可听懂的意群。", (2,)),
    ("phase-3", "Phase 3", "语法与词汇", "把想表达的意思组织成准确、自然的英文。", (3, 4)),
    ("phase-4", "Phase 4", "口语、阅读与写作", "把输入转为能说、能读、能写的输出能力。", (5, 6, 7)),
    ("phase-5", "Phase 5", "真实任务与复习", "在情境中整合能力，并用测试发现下一步。", (8, 9)),
)


@dataclass(frozen=True)
class Unit:
    key: str
    book: int
    title: str
    goal: str
    source: Path
    audio: tuple[tuple[str, str], ...]

    @property
    def path(self) -> str:
        return f"units/{self.key}.html"


def clean_title(value: str) -> str:
    return re.sub(r"^\d\d-\d\d\s+", "", value).strip()


def section_lines(lines: list[str], heading: str) -> list[str]:
    start = next((i + 1 for i, line in enumerate(lines) if line.strip().startswith(heading)), None)
    if start is None:
        return []
    result = []
    for line in lines[start:]:
        if line.strip().startswith("## "):
            break
        result.append(line)
    return result


def goal_from(lines: list[str]) -> str:
    for line in section_lines(lines, "## 1."):
        value = re.sub(r"^[>*\-\s]+", "", line).strip().replace(chr(96), "")
        if value and not value.startswith(chr(96) * 3):
            return value
    return "完成本单元的输入、练习、输出和复习安排。"


def audio_from(lines: list[str]) -> tuple[tuple[str, str], ...]:
    result = []
    for line in section_lines(lines, "## 配套音频"):
        for match in re.finditer(r"\[([^]]+)\]\(([^)]+\.mp3)\)", line):
            label, relative = match.groups()
            result.append((label, "../../" + relative.lstrip("./")))
    return tuple(result)


IPA_EXAMPLES = {
    "i": "see", "ɪ": "sit", "ɛ": "bed", "æ": "cat", "ʌ": "cup", "ə": "about",
    "ɝ": "bird", "ɚ": "teacher", "u": "food", "ʊ": "book", "ɑ": "father", "ɔ": "talk",
    "eɪ": "day", "aɪ": "my", "ɔɪ": "boy", "oʊ": "go", "aʊ": "now",
    "p": "pen", "b": "book", "t": "tea", "d": "day", "k": "key", "g": "go",
    "f": "fan", "v": "van", "θ": "thin", "ð": "this", "s": "see", "z": "zoo",
    "ʃ": "she", "ʒ": "measure", "h": "he", "tʃ": "cheese", "dʒ": "jump",
    "m": "me", "n": "no", "ŋ": "sing", "l": "lee", "r": "red", "j": "yes", "w": "we",
}

def speech_text(value: str) -> str:
    """Return only the pronounceable item, never surrounding lesson prose."""
    stripped = value.strip()
    if stripped.startswith("/") and stripped.endswith("/"):
        token = stripped[1:-1].strip()
        example = IPA_EXAMPLES.get(token.replace("ː", ""))
        return example or ""
    without_ipa = re.sub(r"/[^/\s]+/", " ", value)
    words = re.findall(r"[A-Za-z]+(?:[''-][A-Za-z]+)*", without_ipa)
    if words:
        return " ".join(words)
    ipa_tokens = re.findall(r"/([^/\s]+)/", value)
    examples = [IPA_EXAMPLES.get(token.replace("ː", "")) for token in ipa_tokens]
    if ipa_tokens and all(examples):
        return ", ".join(example for example in examples if example)
    return ""


def listen_button(text: str) -> str:
    if not text:
        return ""
    INLINE_AUDIO_TEXTS.add(text)
    audio_id = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    label = text if len(text) <= 60 else "这段英文"
    return (
        f'<button class="listen-button" type="button" data-audio="../../assets/audio/inline/{audio_id}.mp3" '
        f'aria-label="播放发音：{html.escape(label, quote=True)}" title="播放发音">&#128266;</button>'
    )


def inline_code(value: str) -> str:
    return (
        '<span class="pronunciation"><code>'
        + html.escape(value, quote=False)
        + "</code>"
        + listen_button(speech_text(value))
        + "</span>"
    )


def inline_with_standalone_speech(value: str) -> str:
    rendered = inline(value)
    stripped = value.strip()
    if (
        "data-audio=" in rendered
        or "<code>" in rendered
        or re.search(r"[\u4e00-\u9fff]", value)
        or (stripped.startswith("/") and stripped.endswith("/"))
        or stripped in {"IPA", "SVC", "SVO", "SVOO", "SVOC"}
    ):
        return rendered
    text = speech_text(value)
    if not text:
        return rendered
    return f'<span class="pronunciation">{rendered}{listen_button(text)}</span>'


def table_cell(value: str, fallback_speech: str = "") -> str:
    rendered = inline_with_standalone_speech(value)
    if (
        fallback_speech
        and "data-audio=" not in rendered
        and re.search(r"/[^/]+/", value)
    ):
        return rendered + listen_button(speech_text(fallback_speech))
    return rendered


def discover_units() -> list[Unit]:
    result = []
    for directory in sorted(ROOT.glob("[0-9][0-9]-*")):
        if not directory.is_dir():
            continue
        book = int(directory.name[:2])
        for source in sorted(directory.glob("*.md")):
            if book == 9 and source.name == "README.md":
                continue
            if not re.match(rf"^{book:02d}-\d\d-", source.name):
                continue
            lines = source.read_text(encoding="utf-8").splitlines()
            heading = next((re.match(r"^#\s+(.+)$", line.strip()) for line in lines if line.strip().startswith("# ")), None)
            title = clean_title(heading.group(1) if heading else source.stem)
            result.append(Unit(source.name[:5], book, title, goal_from(lines), source, audio_from(lines)))
    result.sort(key=lambda unit: (unit.book, unit.key))
    if len(result) != 110:
        raise RuntimeError(f"Expected 110 learning units, found {len(result)}")
    return result


def inline(value: str) -> str:
    escaped = html.escape(value, quote=False)

    def markdown_link(match: re.Match[str]) -> str:
        label, href = match.groups()
        href = html.unescape(href)
        if href.lower().endswith(".mp3"):
            return label
        if href.startswith(("https://", "http://")):
            return f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noreferrer">{label}</a>'
        return label

    escaped = re.sub(r"\[([^]]+)\]\(([^)]+)\)", markdown_link, escaped)
    escaped = re.sub(
        chr(96) + r"([^" + chr(96) + r"]+)" + chr(96),
        lambda match: inline_code(html.unescape(match.group(1))),
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)

    def unit_reference(match: re.Match[str]) -> str:
        book, key = match.groups()
        return f'<a href="{key}.html" class="inline-unit-link">Book{book} §{key}</a>'

    return re.sub(r"Book(\d)\s*§(\d\d-\d\d)", unit_reference, escaped)


def split_table(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(line: str) -> bool:
    return bool(split_table(line)) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in split_table(line))


def code_block_html(lines: list[str]) -> str:
    rendered = []
    for line in lines:
        control = listen_button(speech_text(line))
        rendered.append(
            '<span class="code-line"><code>'
            + html.escape(line, quote=False)
            + "</code>"
            + control
            + "</span>"
        )
    return '<pre class="playable-code">' + "".join(rendered) + "</pre>"


def render_markdown(unit: Unit) -> str:
    lines = unit.source.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    i = 0
    in_code = False
    code_lines: list[str] = []
    while i < len(lines):
        raw, stripped = lines[i].rstrip(), lines[i].strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("# "):
            i += 1
            continue
        if stripped.startswith("## 配套音频"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("## "):
                i += 1
            continue
        if stripped.startswith("审查记录："):
            i += 1
            continue
        if stripped.startswith(chr(96) * 3):
            if in_code:
                output.append(code_block_html(code_lines))
                in_code, code_lines = False, []
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(raw)
            i += 1
            continue
        heading = re.match(r"^(#{2,4})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            output.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            rows = [split_table(stripped)]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_table(lines[i]))
                i += 1
            head = "".join(f"<th>{inline_with_standalone_speech(cell)}</th>" for cell in rows[0])
            speech_column = next(
                (index for index, cell in enumerate(rows[0]) if cell.strip() in {"英文", "对比", "单词", "例词"}),
                None,
            )
            body_rows = []
            for row in rows[1:]:
                fallback = row[speech_column] if speech_column is not None and speech_column < len(row) else ""
                cells = "".join(f"<td>{table_cell(cell, fallback)}</td>" for cell in row)
                body_rows.append(f"<tr>{cells}</tr>")
            body = "".join(body_rows)
            output.append(f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
            continue
        if stripped.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i].strip()))
                i += 1
            output.append(f'<aside class="unit-note">{inline(" ".join(quote))}</aside>')
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            output.append("<hr>")
            i += 1
            continue
        unordered, ordered = re.match(r"^[-*+]\s+(.+)$", stripped), re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if unordered or ordered:
            tag = "ul" if unordered else "ol"
            items = []
            while i < len(lines):
                candidate = lines[i].strip()
                match = re.match(r"^[-*+]\s+(.+)$", candidate) if tag == "ul" else re.match(r"^\d+[.)]\s+(.+)$", candidate)
                if not match:
                    break
                items.append(f"<li>{inline_with_standalone_speech(match.group(1))}</li>")
                i += 1
            output.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        paragraph = [stripped]
        i += 1
        while i < len(lines):
            candidate = lines[i].strip()
            if not candidate or re.match(r"^(#{1,6})\s+", candidate) or candidate.startswith((">", "|", chr(96) * 3)) or re.match(r"^[-*+]\s+", candidate) or re.match(r"^\d+[.)]\s+", candidate):
                break
            paragraph.append(candidate)
            i += 1
        output.append(f"<p>{inline_with_standalone_speech(' '.join(paragraph))}</p>")
    return "\n".join(output)


def shell(title: str, body: str, *, depth: int, page: str, unit: Unit | None = None) -> str:
    prefix = "../" * depth
    unit_attr = f' data-unit-id="{unit.key}"' if unit else ""
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#173044"><meta name="description" content="美式英语综合能力训练教材：手机端学习、阶段导航和配套音频播放。">
<link rel="manifest" href="{prefix}manifest.webmanifest"><link rel="icon" href="{prefix}assets/app-icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{prefix}assets/app-icon.svg"><link rel="stylesheet" href="{prefix}assets/styles.css">
<title>{html.escape(title)} · 美式英语综合能力训练</title></head>
<body class="page-{page}" data-root="{prefix}"{unit_attr}>
<header class="site-header"><a class="brand" href="{prefix}index.html" aria-label="返回课程首页"><span>AE</span><strong>英语学习</strong></a>
<nav aria-label="主导航"><a href="{prefix}plan.html">路线</a><a href="{prefix}index.html#books">目录</a></nav></header>
{body}<script src="{prefix}assets/course-data.js"></script><script src="{prefix}assets/app.js"></script></body></html>"""


def phase_for(book: int) -> tuple[str, str, str]:
    for phase_id, label, title, _description, books in PHASES:
        if book in books:
            return phase_id, label, title
    raise ValueError(book)


def unit_link(unit: Unit, depth: int) -> str:
    return f"{'../' * depth}{unit.path}"


def unit_row(unit: Unit, depth: int, show_book: bool = False) -> str:
    book_label = f'<span class="unit-book">Book{unit.book}</span>' if show_book else ""
    return f"""<a class="unit-row" href="{unit_link(unit, depth)}" data-unit="{unit.key}">
<span class="unit-number">{unit.key.split('-')[1]}</span><span class="unit-copy">{book_label}<strong>{html.escape(unit.title)}</strong><small>{html.escape(unit.goal)}</small></span><span class="unit-state">未学习</span></a>"""


def write_home(units: list[Unit]) -> None:
    phases = []
    for phase_id, label, title, description, books in PHASES:
        phases.append(f'<a class="phase-row" href="plan.html#{phase_id}"><span class="phase-number">{label[-1]}</span><span><small>{label} · {" · ".join(f"Book{b}" for b in books)}</small><strong>{title}</strong><em>{description}</em></span><span class="arrow">↗</span></a>')
    books = []
    for book, (title, description) in BOOKS.items():
        count = sum(unit.book == book for unit in units)
        phase_id, phase_label, _ = phase_for(book)
        books.append(f'<a class="book-row" href="books/book{book}.html" data-book="{book}" data-phase="{phase_id}"><span><small>{phase_label} · {count} 个单元</small><strong>Book{book} · {title}</strong><em>{description}</em></span><span class="book-progress" data-book-counter="{book}">0/{count}</span></a>')
    body = f"""<main><section class="home-intro"><div class="home-orbit" aria-hidden="true"></div><p class="eyebrow">American English Integrated Course</p>
<h1>美式英语<br>综合能力训练</h1><p class="home-lead">按阶段学习、按单元完成；例句与练习音频可以直接在手机上播放。</p>
<div class="home-actions"><a class="button button-primary" data-continue href="units/{units[0].key}.html">开始学习</a><a class="text-action" href="plan.html">查看完整路线 <span>→</span></a></div>
<div class="home-progress"><span>已完成</span><strong data-course-progress>0 / {len(units)} 个单元</strong><i><b data-progress-bar></b></i></div></section>
<section class="section-block"><div class="section-heading"><p class="eyebrow">按阶段学习</p><h2>知道下一步，而不是在 PDF 里翻找</h2></div><div class="phase-list">{''.join(phases)}</div></section>
<section class="section-block course-books" id="books"><div class="section-heading"><p class="eyebrow">完整目录</p><h2>从 Book0 到 Book9</h2></div><div class="book-list">{''.join(books)}</div></section>
<section class="home-help"><p class="eyebrow">使用提示</p><h2>每次只做一个单元</h2><p>先听或读输入内容，再完成练习和输出任务。标记完成后，网站会在本机保存进度，并自动为你指向下一个未完成单元。</p></section></main>"""
    (SITE / "index.html").write_text(shell("首页", body, depth=0, page="home"), encoding="utf-8")


def write_plan(units: list[Unit]) -> None:
    sections = []
    for position, (phase_id, label, title, description, books) in enumerate(PHASES):
        phase_units = [unit for unit in units if unit.book in books]
        rows = "".join(unit_row(unit, 0, len(books) > 1) for unit in phase_units)
        open_attr = " open" if position == 0 else ""
        sections.append(f'<details class="phase-plan" id="{phase_id}"{open_attr}><summary><span><small>{label} · {", ".join(f"Book{b}" for b in books)}</small><strong>{title}</strong></span><span class="summary-mark">+</span></summary><p>{description}</p><div class="unit-list">{rows}</div></details>')
    body = f"""<main class="plan-page"><section class="page-intro"><p class="eyebrow">学习路线</p><h1>按推荐顺序，<br>一步一步走。</h1><p>不需要同时学习所有模块。完成每个单元的输出任务后，再依照“下一步”进入下一个单元或相关能力模块。</p><a class="button button-primary" data-continue href="units/{units[0].key}.html">继续我的学习</a></section><section class="plan-list">{''.join(sections)}</section></main>"""
    (SITE / "plan.html").write_text(shell("学习路线", body, depth=0, page="plan"), encoding="utf-8")


def write_books(units: list[Unit]) -> None:
    for book, (title, description) in BOOKS.items():
        book_units = [unit for unit in units if unit.book == book]
        phase_id, label, phase_title = phase_for(book)
        rows = "".join(unit_row(unit, 1) for unit in book_units)
        next_html = f'<a class="text-action" href="book{book + 1}.html">下一册：Book{book + 1} · {BOOKS[book + 1][0]} <span>→</span></a>' if book < 9 else '<a class="text-action" href="../plan.html">回到完整学习路线 <span>→</span></a>'
        body = f"""<main class="book-page"><section class="book-hero"><a class="back-link" href="../plan.html#{phase_id}">← 返回学习路线</a><p class="eyebrow">{label} · {phase_title}</p><h1>Book{book}<br>{title}</h1><p>{description}</p><div class="book-hero-progress"><span>本册进度</span><strong data-book-progress="{book}">0 / {len(book_units)}</strong><i><b data-book-progress-bar="{book}"></b></i></div></section><section class="book-units"><div class="section-heading"><p class="eyebrow">按顺序学习</p><h2>{len(book_units)} 个学习单元</h2></div><div class="unit-list">{rows}</div></section><footer class="book-footer">{next_html}</footer></main>"""
        (BOOKS_DIR / f"book{book}.html").write_text(shell(f"Book{book} {title}", body, depth=1, page="book"), encoding="utf-8")


def write_units(units: list[Unit]) -> None:
    for position, unit in enumerate(units):
        phase_id, label, phase_title = phase_for(unit.book)
        previous = units[position - 1] if position else None
        following = units[position + 1] if position + 1 < len(units) else None
        prev_html = f'<a class="previous" href="{previous.key}.html"><small>上一单元</small><strong>← {html.escape(previous.title)}</strong></a>' if previous else '<a class="previous" href="../plan.html"><small>返回</small><strong>← 学习路线</strong></a>'
        next_html = f'<a class="next" href="{following.key}.html"><small>下一单元</small><strong>{html.escape(following.title)} →</strong></a>' if following else '<a class="next" href="../plan.html"><small>完成课程</small><strong>回到学习路线 →</strong></a>'
        body = f"""<main class="unit-page"><div class="unit-crumb"><a href="../books/book{unit.book}.html">Book{unit.book}</a><span>/</span><span>{unit.key}</span></div><section class="unit-hero"><p class="eyebrow">{label} · {phase_title}</p><h1>{unit.key}<br>{html.escape(unit.title)}</h1><p>{inline(unit.goal)}</p><div class="unit-actions"><button class="complete-button" type="button" data-mark-complete data-unit="{unit.key}">标记本单元完成</button></div></section><article class="reading-content">{render_markdown(unit)}</article><nav class="unit-pagination" aria-label="单元导航">{prev_html}{next_html}</nav></main><aside class="reading-tools" aria-label="阅读设置"><span>阅读大小</span><button type="button" data-font-size="small">A−</button><button type="button" data-font-size="normal">A</button><button type="button" data-font-size="large">A+</button></aside>"""
        (UNITS_DIR / f"{unit.key}.html").write_text(shell(f"{unit.key} {unit.title}", body, depth=1, page="unit", unit=unit), encoding="utf-8")


def write_assets(units: list[Unit]) -> None:
    payload = {"units": [{"id": unit.key, "book": unit.book, "title": unit.title, "path": unit.path} for unit in units], "phases": [{"id": phase_id, "label": label, "title": title, "books": list(books)} for phase_id, label, title, _description, books in PHASES]}
    (ASSETS / "course-data.js").write_text("window.COURSE = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    inline_manifest = {
        "generator": "build_mobile_site.py",
        "items": [
            {
                "id": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                "text": text,
                "file": f"assets/audio/inline/{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}.mp3",
            }
            for text in sorted(INLINE_AUDIO_TEXTS, key=str.casefold)
        ],
    }
    INLINE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "assets" / "inline-audio-manifest.json").write_text(
        json.dumps(inline_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pages = ["./", "./index.html", "./plan.html", "./manifest.webmanifest", "./assets/styles.css", "./assets/app.js", "./assets/course-data.js", "./assets/app-icon.svg"]
    pages += [f"./books/book{number}.html" for number in BOOKS] + [f"./{unit.path}" for unit in units]
    (SITE / "sw.js").write_text(f"""const CACHE_NAME = "ae-course-mobile-v6";
const PRECACHE = {json.dumps(pages, ensure_ascii=False)};
self.addEventListener("install", (event) => {{ event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE))); self.skipWaiting(); }});
self.addEventListener("activate", (event) => {{ event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))); self.clients.claim(); }});
self.addEventListener("fetch", (event) => {{ const request = event.request; const url = new URL(request.url); if (url.origin !== self.location.origin || request.method !== "GET") return; if (request.destination === "audio") {{ event.respondWith(fetch(request).catch(() => caches.match(request))); return; }} event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => {{ const copy = response.clone(); caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)); return response; }}))); }});
""", encoding="utf-8")
    (SITE / "manifest.webmanifest").write_text(json.dumps({"name": "美式英语综合能力训练", "short_name": "英语学习", "start_url": "./", "display": "standalone", "background_color": "#f6f2ea", "theme_color": "#173044", "lang": "zh-CN", "icons": [{"src": "assets/app-icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    INLINE_AUDIO_TEXTS.clear()
    units = discover_units()
    for directory in (SITE, ASSETS, UNITS_DIR, BOOKS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    write_home(units)
    write_plan(units)
    write_books(units)
    write_units(units)
    write_assets(units)
    print(f"Built mobile PWA: {len(units)} unit pages, {len(BOOKS)} book pages")


if __name__ == "__main__":
    main()
