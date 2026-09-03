"""Build searchable indexes for the integrated English course.

Grammar and speaking indexes keep recommended material separate from
``常见错误`` tables, so an error example is never presented as a model.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = ROOT / "indexes"


def clean(value: str) -> str:
    value = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"[*_`]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def md_cell(value: str) -> str:
    """Clean a cell and keep it safe inside a Markdown table."""
    return clean(value).replace("|", r"\|")


def write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def split_row(line: str) -> list[str]:
    value = line.strip().strip("|")
    return [cell.strip().replace("`", "") for cell in value.split("|")]


def tables(path: Path):
    """Yield ``(heading, rows)`` for Markdown tables and their nearest H2."""
    lines = path.read_text(encoding="utf-8").splitlines()
    current_h2 = ""
    i = 0
    while i < len(lines) - 1:
        heading_match = re.match(r"^##\s+(.+)$", lines[i].strip())
        if heading_match:
            current_h2 = heading_match.group(1).strip()
        if lines[i].strip().startswith("|") and re.search(r"\|\s*:?-{3,}:?\s*", lines[i + 1]):
            rows = [split_row(lines[i])]
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(split_row(lines[j]))
                j += 1
            if len(rows) > 1:
                yield current_h2, rows
            i = j
            continue
        i += 1


def h1_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#\s+(\d\d-\d\d)\s+(.+)$", line.strip())
        if match:
            return match.group(2).strip()
    return path.stem


def link(directory: str, source: Path, label: str | None = None) -> str:
    return f"[{label or source.name[:5]}](../{directory}/{source.name})"


def build_vocabulary() -> int:
    base = ROOT / "04-Vocabulary-and-Collocations"
    files = {source.stem[:5]: source for source in sorted(base.glob("*.md"))}
    rows: dict[str, tuple[str, str, str]] = {}
    for section, source in files.items():
        for _heading, table in tables(source):
            header = [clean(cell) for cell in table[0]]
            if not header or header[0] not in {"词语", "短语", "搭配", "表达"}:
                continue
            for row in table[1:]:
                if len(row) < 2:
                    continue
                term = clean(row[0])
                if not term or term.startswith("---"):
                    continue
                ipa = clean(row[1])
                collocation = clean(row[2]) if len(row) > 2 else ""
                note = "; ".join(part for part in (ipa, collocation) if part)
                rows.setdefault(term.lower(), (term, section, note))

    lines = [
        "# 词汇、搭配和短语动词索引",
        "",
        "> 来源：Book4 核心词汇、搭配与短语动词。按词语字母顺序排列；同一词语只保留一个主要入口，具体语境以正文为准。",
        "",
        "| 词语 | 首选章节 | IPA/提示 |",
        "| --- | --- | --- |",
    ]
    for key in sorted(rows):
        term, section, note = rows[key]
        source = files[section]
        lines.append(f"| {md_cell(term)} | {link('04-Vocabulary-and-Collocations', source)} | {md_cell(note)} |")
    write(INDEX_DIR / "vocabulary-index.md", lines)
    return len(rows)


# Stable learning targets, rather than every label in an exercise or answer.
GRAMMAR_TOPICS: dict[str, list[str]] = {
    "03-01": ["主语、动词、宾语、补语与状语", "六种基本句型：SV、SVC、SVA、SVO、SVOO、SVOC"],
    "03-02": ["be 动词：am/is/are", "一般现在时：习惯、事实与稳定状态", "第三人称单数 -s", "do/does 否定与疑问"],
    "03-03": ["一般过去时", "过去进行时：was/were + -ing", "when/while 背景与插入事件"],
    "03-04": ["现在进行时", "will：临时决定、预测与承诺", "be going to：意图与迹象预测", "现在进行时表达已安排将来"],
    "03-05": ["现在完成时：经历、持续与结果", "for/since 与持续时间", "现在完成时和一般过去时的区别"],
    "03-06": ["be、do/does/did 的否定与疑问", "情态动词的否定与疑问", "Wh- 问句语序", "现在完成时的否定"],
    "03-07": ["can/could/may/might 的可能性与请求", "must/have to/should 的义务与建议", "情态动词后的动词原形", "礼貌请求的语气梯度"],
    "03-08": ["可数名词与不可数名词", "a/an/the：首次提到与特指", "some/any/many/much 与数量", "零冠词与一般概念"],
    "03-09": ["主格、宾格、物主代词与反身代词", "时间和地点介词", "并列与原因、转折、条件连词"],
    "03-10": ["比较级与最高级", "because/because of 原因", "if 条件句", "so/therefore 结果表达"],
    "03-11": ["who/which/that/where 定语从句", "限制性与非限制性从句", "间接问题的陈述语序", "间接礼貌请求"],
    "03-12": ["be + 过去分词的被动语态", "不同时态的被动结构", "by + 执行者", "口语省略与正式书面语"],
}


def error_tables(source: Path):
    for heading, table in tables(source):
        if not re.search(r"常见错误|错误提醒", heading):
            continue
        header = [clean(cell) for cell in table[0]]
        if not header or header[0] not in {"错误", "问题", "不推荐表达"}:
            continue
        for row in table[1:]:
            if len(row) >= 2 and clean(row[0]) and not clean(row[0]).startswith("---"):
                yield row


def build_grammar() -> tuple[int, int]:
    base = ROOT / "03-Practical-Grammar"
    files = {source.stem[:5]: source for source in sorted(base.glob("*.md"))}
    lines = [
        "# 语法索引",
        "",
        "> 来源：Book3 实用语法与句子构造。主表只列推荐学习主题；易错句单独列在文末，避免把错误表达误当成范例。",
        "",
        "## 推荐语法主题",
        "",
        "| 主题 | 首选章节 | 正文 |",
        "| --- | --- | --- |",
    ]
    for section in sorted(GRAMMAR_TOPICS):
        source = files.get(section)
        if not source:
            continue
        for topic in GRAMMAR_TOPICS[section]:
            lines.append(f"| {md_cell(topic)} | {section} | {link('03-Practical-Grammar', source)} |")

    error_count = 0
    lines += ["", "## 常见易错表达（复习用）", "", "> 下表中的左栏是需要改正或辨析的示例，不是推荐表达。", "", "| 易错表达 | 推荐改法 | 首选章节 |", "| --- | --- | --- |"]
    for section in sorted(files):
        for row in error_tables(files[section]):
            lines.append(f"| {md_cell(row[0])} | {md_cell(row[1])} | {section} |")
            error_count += 1
    write(INDEX_DIR / "grammar-index.md", lines)
    return sum(len(topics) for topics in GRAMMAR_TOPICS.values()), error_count


def build_speaking() -> tuple[int, int]:
    base = ROOT / "05-Speaking-Patterns"
    files = {source.stem[:5]: source for source in sorted(base.glob("*.md"))}
    lines = [
        "# 口语表达索引",
        "",
        "> 来源：Book5 高频口语句型。主表列功能和推荐句型；常见错误单独列出。正式程度和自然变体请回到正文确认。",
        "",
        "## 交际功能与推荐句型",
        "",
        "| 功能 | 推荐句型/入口 | 首选章节 | 正文 |",
        "| --- | --- | --- | --- |",
    ]
    core_count = 0
    for section in sorted(files):
        source = files[section]
        for heading, table in tables(source):
            if not re.match(r"2\.\s*核心句型", heading):
                continue
            header = [clean(cell) for cell in table[0]]
            if not header or header[0] not in {"功能", "意图"}:
                continue
            for row in table[1:]:
                if len(row) < 2 or not clean(row[0]) or clean(row[0]).startswith("---"):
                    continue
                lines.append(f"| {md_cell(row[0])} | {md_cell(row[1])} | {section} | {link('05-Speaking-Patterns', source)} |")
                core_count += 1
    error_count = 0
    lines += ["", "## 常见易错表达（复习用）", "", "> 下表中的左栏是需要改正、补充或调整语气的示例，不是推荐表达。", "", "| 易错表达/问题 | 推荐改法或处理 | 首选章节 |", "| --- | --- | --- |"]
    for section in sorted(files):
        for row in error_tables(files[section]):
            lines.append(f"| {md_cell(row[0])} | {md_cell(row[1])} | {section} |")
            error_count += 1
    write(INDEX_DIR / "speaking-index.md", lines)
    return core_count, error_count


# The pronunciation chapters introduce these symbols explicitly.  Keeping a
# teaching map prevents a sentence-level IPA transcription from creating
# misleading duplicate entries in the index.
IPA_TOPICS: dict[str, list[str]] = {
    "01-02": ["i", "ɪ", "ɛ", "æ"],
    "01-03": ["ʌ", "ə", "ɝ", "ɚ"],
    "01-04": ["u", "ʊ", "ɑ", "ɔ"],
    "01-05": ["eɪ", "aɪ", "ɔɪ", "oʊ", "aʊ"],
    "01-06": ["p", "b", "t", "d", "k", "ɡ"],
    "01-07": ["f", "v", "θ", "ð", "s", "z", "ʃ", "ʒ", "tʃ", "dʒ"],
    "01-08": ["m", "n", "ŋ", "l", "ɹ", "j", "w"],
}


def build_ipa() -> int:
    base = ROOT / "01-Pronunciation"
    files = {source.stem[:5]: source for source in sorted(base.glob("*.md"))}
    symbols: dict[str, str] = {
        symbol: section for section, values in IPA_TOPICS.items() for symbol in values
    }
    lines = [
        "# IPA 音素索引",
        "",
        "> 来源：Book1 美式英语发音基础。只从发音教学表提取符号；重音、变体和例词请回到正文确认。",
        "",
        "| IPA 符号 | 首次重点章节 | 章节作用 |",
        "| --- | --- | --- |",
    ]
    for symbol in sorted(symbols):
        section = symbols[symbol]
        source = files[section]
        lines.append(f"| `{md_cell('/' + symbol + '/')}` | {section} | {link('01-Pronunciation', source)}：{md_cell(h1_title(source))} |")
    write(INDEX_DIR / "ipa-index.md", lines)
    return len(symbols)


def main() -> None:
    grammar_topics, grammar_errors = build_grammar()
    speaking_core, speaking_errors = build_speaking()
    counts = {
        "vocabulary": build_vocabulary(),
        "grammar_topics": grammar_topics,
        "grammar_errors": grammar_errors,
        "speaking_patterns": speaking_core,
        "speaking_errors": speaking_errors,
        "ipa": build_ipa(),
    }
    print(counts)


if __name__ == "__main__":
    main()
