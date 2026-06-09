#!/usr/bin/env python3
"""
Books watcher — detects new books in Dropbox/Books and Reeden,
appends them to My Books.md in the Obsidian vault.
Runs every 8 hours via launchd.
"""

import json
import os
import re
import zipfile
from datetime import date
from pathlib import Path

# --- Paths ---
DROPBOX_BOOKS = Path("<dropbox>/Books")
REEDEN_BOOKS  = Path("<dropbox>/Apps/Reeden/Reeden/books")
MY_BOOKS_MD   = Path("<vault>/10-Research/My-readings/My Books.md")
STATE_FILE    = Path("<watcher-dir>/books-state.json")

BOOK_EXTENSIONS = {'.pdf', '.epub', '.mobi', '.azw'}  # .acsm excluded — it's a download token, not a book

# Files/patterns to skip (not real books)
SKIP_NAMES = ['chapter-', 'appendix ', 'glossika', 'ofl', 'readme', '便簽', 'solution manual']

# --- Category inference ---
# Each entry: (list of keywords, category)
CATEGORY_RULES = [
    (["blindsight", "echopraxia", "ubik", "androids dream", "do androids", "foundation",
      "never flinch", "selected stories", "collected stories", "het diner", "oeroeg",
      "alice", "max havelaar", "fanhua", "芳华", "丁丁", "卡梅拉", "philip k. dick",
      "peter watts", "stephen king", "lewis carroll", "herman koch", "hella haasse",
      "isaac asimov", "asimov", "science fiction"], "Fiction"),

    (["jung", "red book", "archetypes", "collective unconscious", "memories dreams",
      "man and his symbols", "denial of death", "road less traveled", "identity trap",
      "righteous mind", "future of nostalgia", "antifragile", "反脆弱", "自卑與超越",
      "覺醒", "中年之路", "榮格", "多模型思維", "a life of meaning", "james hollis",
      "ernest becker", "nassim", "philosophy"], "Philosophy"),

    (["leadership", "dare to lead", "leading change", "real-time leadership", "compassionate",
      "managing oneself", "drucker", "hbr", "harvard business", " mba", "strategy",
      "execution", "good work", "working identity", "why managers", "peter senge",
      "fifth discipline", "sixth discipline", "six disciplines", "exactly what to say",
      "supercommunicators", "only the paranoid", "power why some", "jeffrey pfeffer",
      "kotter", "上位思維", "大人學", "執行長日記", "成法", "稻盛", "世界管理",
      "精讀杜拉克", "經理人", "讓任何人都聽", "領導者的說話", "30天精读", "mba轻松读",
      "查爾斯河畔", "你永遠有更好", "大格局大思維", "發現我的多重職涯", "john kotter",
      "brené brown", "peter drucker", "managing successful programme", "axelos"], "Leadership & Strategy"),

    (["project management", "prince2", "okr", "radical focus", "measure what matters",
      "ai revolution in project", "project management with ai", "專案管理革命", "超級專案管理",
      "digital transformation playbook", "bent flyvbjerg", "managing successful project"],
     "Project Management"),

    (["economics", "economic growth", "nations fail", "power and progress", "power progress",
      "entrepreneurial state", "limits to growth", "world dynamics", "schumpeter",
      "how countries go broke", "principles for navigating big debt",
      "great divergence", "great wave", "hundred-year marathon", "power of creative destruction",
      "introduction to economic", "why nations fail", "small island", "人性賽局", "國家為什麼",
      "小島經濟學", "耶魯最受歡迎", "經濟學的世界", "自由的窄廊", "權力與進步",
      "mazzucato", "aghion", "acemoglu", "mankiw", "principles of economics",
      "everything is predictable", "bayesian"], "Economics"),

    (["geopolitics", "spies", "on china", "kissinger", "thucydides", "cold war",
      "great powers", "rise and fall of the great", "hundred-year marathon",
      "成為歐洲人", "李光耀觀天下", "活在美國世紀", "世界秩序", "world order",
      "destined for war", "calder walton", "paul kennedy", "graham allison",
      "henry kissinger", "joseph nye", "how states think"], "Geopolitics"),

    (["psychology", "wellbeing", "emotional intelligence", "primal leadership", "goleman",
      "chimp paradox", "influence", "cialdini", "talking to strangers", "difficult conversations",
      "nonviolent communication", "optimal", "sovereign", "how to know a person",
      "5 types of wealth", "good enough job", "最佳狀態", "malcolm gladwell",
      "revenge of the tipping point", "daniel goleman", "sahil bloom", "simone stolzoff",
      "emma seppala", "jonathan haidt", "david brooks"], "Psychology & Wellbeing"),

    (["productivity", "self-help", "deep work", "essentialism", "dopamine detox",
      "great mental models", "personal mba", "naval", "pathless path", "10x成長", "10倍",
      "別對每件事", "納瓦爾", "cal newport", "greg mckeown", "shane parrish",
      "josh kaufman", "paul millerd", "m. scott peck", "good enough job",
      "what color is your parachute", "art of doing science", "hamming",
      "art of persuasion", "herminia ibarra", "working identity"], "Productivity & Self-Help"),

    (["parenting", "child", "更少但更好的养育"], "Parenting"),

    (["computer science", "artificial intelligence", "machine learning", "singularity",
      "nexus", "brave new words", "how to create a mind", "hbr guide to ai",
      "ai and economic", "kurzweil", "fei-fei li", "worlds i see", "salman khan",
      "yuval noah harari", "ray kurzweil"], "Computer Science & AI"),

    (["science and civilisation in china", "needham", "reinventing the chinese city",
      "中國歷代政治得失", "地藏菩萨", "張忠謀", "松下幸之助自传", "黃仁勳",
      "biography", "自传", "autobio", "source code bill gates", "錢穆",
      "governance of european higher education"], "Reference"),
]

def guess_category(title: str, author: str = "") -> str:
    text = (title + " " + author).lower()
    for keywords, category in CATEGORY_RULES:
        if any(kw.lower() in text for kw in keywords):
            return category
    return "Reference"


# --- State ---
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {"dropbox_files": [], "reeden_ids": []}
    return {"dropbox_files": [], "reeden_ids": []}

def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


# --- Scanning ---
def scan_dropbox() -> list:
    files = []
    for ext in BOOK_EXTENSIONS:
        files.extend(DROPBOX_BOOKS.rglob(f"*{ext}"))
    return sorted(files)

def scan_reeden() -> list:
    """Return list of dicts with id, title, author extracted from EPUB files."""
    if not REEDEN_BOOKS.exists():
        return []
    results = []
    for epub_path in REEDEN_BOOKS.iterdir():
        if not epub_path.is_file():
            continue
        try:
            with zipfile.ZipFile(str(epub_path)) as z:
                opf_path = next((n for n in z.namelist() if n.endswith('.opf')), None)
                if not opf_path:
                    continue
                opf = z.read(opf_path).decode('utf-8', errors='ignore')
                title_m  = re.search(r'<dc:title[^>]*>([^<]+)', opf)
                author_m = re.search(r'<dc:creator[^>]*>([^<]+)', opf)
                title  = title_m.group(1).strip() if title_m else ""
                author = author_m.group(1).strip() if author_m else ""
                if title:
                    results.append({"id": epub_path.name, "title": title,
                                    "author": author, "type": "epub"})
        except Exception:
            continue
    return results


# --- Parsing ---
def parse_dropbox_file(path: Path) -> dict:
    name = path.stem
    author = ""
    title = name
    if " - " in name:
        parts = name.rsplit(" - ", 1)
        title = parts[0].strip()
        author = parts[1].strip()
    # Clean title
    title = re.sub(r'\s+', ' ', title).strip()
    # Category from subfolder; root-level files get inferred category
    parent = path.parent.name
    category = parent if parent != "Books" else guess_category(title, author)
    fmt = path.suffix.upper().lstrip('.')
    return {"title": title, "author": author, "category": category,
            "format": fmt, "source": "Dropbox", "status": "unread"}

def parse_reeden_book(book: dict) -> dict:
    title = book.get('title', '').strip()
    author = book.get('author', '').strip()
    fmt = book.get('type', 'epub').upper()
    category = guess_category(title, author)
    return {"title": title, "author": author, "category": category,
            "format": fmt, "source": "Reeden", "status": "unread"}

def should_skip(name: str) -> bool:
    name_lower = name.lower()
    return any(p in name_lower for p in SKIP_NAMES)


# --- My Books.md update ---
def parse_all_books(content: str):
    """Parse the category-sectioned file. Returns (grouped, fmt_hint).
    grouped: {category: [row_columns, ...]}
    fmt_hint: 'callout' (file uses '> [!note]- Category' callouts) or 'plain' ('## Category' tables)
    Recognises both formats, preserves all columns (including 📖/📁 link cells)."""
    grouped = {}
    current_cat = None
    fmt_hint = 'plain'  # default; switched to 'callout' on first sighting

    for line in content.split('\n'):
        is_callout_line = line.startswith('>')
        body = line[1:].lstrip() if is_callout_line else line

        m_callout = re.match(r'^\[!note\][-+]?\s+(.+?)\s*$', body)
        m_plain   = re.match(r'^##\s+(.+?)\s*$', line)
        if m_callout:
            current_cat = m_callout.group(1).strip()
            grouped.setdefault(current_cat, [])
            fmt_hint = 'callout'
            continue
        if m_plain:
            current_cat = m_plain.group(1).strip()
            grouped.setdefault(current_cat, [])
            continue

        if (current_cat and body.startswith('|')
              and not re.match(r'^\|\s*[-:]+', body)
              and not re.match(r'^\|\s*Title', body)):
            parts = body.split('|')
            cols = [c.strip() for c in parts[1:-1]] if len(parts) >= 3 else []
            if len(cols) >= 5:
                grouped[current_cat].append(cols)
    return grouped, fmt_hint

def build_sections(grouped: dict, fmt_hint: str = 'callout') -> str:
    lines = []
    if fmt_hint == 'callout':
        for cat in sorted(grouped.keys()):
            lines.append(f'> [!note]- {cat}')
            lines.append('>')
            max_cols = max((len(r) for r in grouped[cat]), default=6)
            if max_cols >= 8:
                lines.append('> | Title | Author | Format | Source | Status | ⭐ | 📖 | 📁 |')
                lines.append('> | --- | --- | --- | --- | --- | --- | --- | --- |')
            elif max_cols >= 6:
                lines.append('> | Title | Author | Format | Source | Status | ⭐ |')
                lines.append('> | --- | --- | --- | --- | --- | --- |')
            else:
                lines.append('> | Title | Author | Format | Source | Status |')
                lines.append('> | --- | --- | --- | --- | --- |')
            for row in sorted(grouped[cat], key=lambda r: r[0].lower()):
                padded = list(row) + [''] * (max_cols - len(row))
                lines.append('> | ' + ' | '.join(padded) + ' |')
            lines.append('')
        return '\n'.join(lines)

    for cat in sorted(grouped.keys()):
        lines.append(f'## {cat}')
        lines.append('')
        lines.append('| Title | Author | Format | Source | Status | ⭐ |')
        lines.append('| --- | --- | --- | --- | --- | --- |')
        for row in sorted(grouped[cat], key=lambda r: r[0].lower()):
            title  = row[0]
            author = row[1] if len(row) > 1 else ''
            fmt    = row[2] if len(row) > 2 else ''
            source = row[3] if len(row) > 3 else ''
            status = row[4] if len(row) > 4 else 'unread'
            fav    = row[5] if len(row) > 5 else ''
            lines.append(f'| {title} | {author} | {fmt} | {source} | {status} | {fav} |')
        lines.append('')
    return '\n'.join(lines)

def update_my_books(new_entries: list) -> int:
    """Returns N>=0 added, or -1 if safety guard fired (caller MUST NOT save state)."""
    content = MY_BOOKS_MD.read_text(encoding='utf-8')
    grouped, fmt_hint = parse_all_books(content)

    fm_match = re.match(r'(---.*?---)', content, re.DOTALL)
    frontmatter = fm_match.group(1) if fm_match else ''

    # Safety guard: refuse to rewrite if the parser drastically under-reports vs frontmatter total.
    # Without this, a parser bug or format drift would silently wipe the file (regression on 2026-05-05).
    seen = sum(len(v) for v in grouped.values())
    declared = 0
    m_total = re.search(r'^total:\s*(\d+)', frontmatter, re.MULTILINE)
    if m_total: declared = int(m_total.group(1))
    if declared > 50 and seen < declared * 0.5:
        alert = (f"[books-watcher] SAFETY GUARD: parser saw {seen} rows but frontmatter "
                 f"declares total={declared}. Refusing to rewrite My Books.md "
                 f"(would risk losing {declared - seen} rows). Investigate the parser/format mismatch.")
        try:
            log = STATE_FILE.parent / 'books-watcher-alert.log'
            with log.open('a', encoding='utf-8') as f:
                f.write(alert + '\n')
        except Exception:
            pass
        print(alert)
        return -1

    existing_titles = {r[0].lower() for rows in grouped.values() for r in rows}

    added = 0
    for entry in new_entries:
        if entry['title'].lower() not in existing_titles:
            cat = entry['category']
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append([entry['title'], entry['author'],
                                  entry['format'], entry['source'], entry['status'], ''])
            existing_titles.add(entry['title'].lower())
            added += 1

    if added == 0:
        return 0

    total = sum(len(v) for v in grouped.values())
    today = date.today().isoformat()
    frontmatter = re.sub(r'total:\s*\d+', f'total: {total}', frontmatter)
    frontmatter = re.sub(r'updated:\s*[\d-]+', f'updated: {today}', frontmatter)

    intro = 'A catalog of books across Dropbox/Books and Reeden, organized by category.'
    new_content = frontmatter + '\n\n' + intro + '\n\n' + build_sections(grouped, fmt_hint)
    MY_BOOKS_MD.write_text(new_content, encoding='utf-8')
    return added


# --- Main ---
def main():
    state = load_state()
    known_dropbox = set(state.get("dropbox_files", []))
    known_reeden  = set(state.get("reeden_ids", []))

    new_entries = []

    # Dropbox/Books
    for path in scan_dropbox():
        path_str = str(path)
        if path_str not in known_dropbox:
            known_dropbox.add(path_str)
            if should_skip(path.name):
                continue
            new_entries.append(parse_dropbox_file(path))

    # Reeden
    for book in scan_reeden():
        bid = book.get('id', '')
        if bid not in known_reeden:
            known_reeden.add(bid)
            title = book.get('title', '').strip()
            if not title or should_skip(title):
                continue
            new_entries.append(parse_reeden_book(book))

    added = update_my_books(new_entries) if new_entries else 0

    if added == -1:
        # Safety guard fired — DO NOT save state, otherwise new files would be marked
        # known but never registered in My Books.md. Bail out so user can inspect.
        print("[books-watcher] Aborted run; state not updated. See books-watcher-alert.log.")
        return

    save_state({"dropbox_files": list(known_dropbox), "reeden_ids": list(known_reeden)})

    if added > 0:
        print(f"[books-watcher] Added {added} new book(s) to My Books.md")
    else:
        print("[books-watcher] No new books found")


if __name__ == "__main__":
    main()
