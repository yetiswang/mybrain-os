"""
import_rabobank.py — Parse Rabobank PDF bank statements into SQLite.
"""

import argparse
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pdfplumber

DB_PATH = Path(os.environ.get("RABOBANK_DB", str(Path.home() / ".local/share/rabobank.db")))
DROP_FOLDER = Path(os.environ.get("RABOBANK_DROP_FOLDER", str(Path.home() / "Documents/Finance")))
STATEMENT_FILE_RE = re.compile(
    r"^(Rekeningafschriften-.*|Creditcard overzichten_.*)\.pdf$",
    re.IGNORECASE,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE    NOT NULL,
    amount          REAL    NOT NULL,
    currency        TEXT    NOT NULL DEFAULT 'EUR',
    counterparty    TEXT,
    description     TEXT,
    category        TEXT,
    iban_from       TEXT,
    iban_to         TEXT,
    balance_after   REAL,
    raw_text        TEXT,
    source_file     TEXT    NOT NULL,
    UNIQUE(date, amount, counterparty, description, source_file)
);
CREATE INDEX IF NOT EXISTS idx_tx_date         ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_counterparty ON transactions(counterparty);
CREATE INDEX IF NOT EXISTS idx_tx_category     ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_tx_source       ON transactions(source_file);

CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    parent_category TEXT
);
CREATE TABLE IF NOT EXISTS recurring_bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    counterparty TEXT NOT NULL, category TEXT,
    expected_amount REAL, frequency TEXT CHECK(frequency IN ('monthly','quarterly','yearly')),
    last_seen DATE, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL, imported_at DATETIME NOT NULL DEFAULT (datetime('now')),
    row_count INTEGER NOT NULL DEFAULT 0, date_range TEXT
);
CREATE INDEX IF NOT EXISTS idx_import_filename ON import_log(filename);
"""

DEFAULT_CATEGORIES = [
    ("Mortgage", "Housing"), ("Energy", "Housing"), ("Insurance", "Housing"),
    ("Municipal taxes", "Housing"), ("Water", "Housing"), ("Internet", "Housing"),
    ("Solar loan", "Housing"), ("Home maintenance", "Housing"), ("Renovation", "Housing"),
    ("Groceries", None), ("Transport", None), ("Subscriptions", None),
    ("Healthcare", None), ("Dining", None), ("Shopping", None),
    ("Salary", "Income"), ("Other income", "Income"), ("Savings", None),
    ("Childcare", None), ("Transfer", None), ("Leisure", None), ("Charity", None),
    ("Kids", None), ("Remittances", None), ("Government", None), ("Cash withdrawal", None),
    ("Credit card", None), ("Banking fees", None), ("Travel", None), ("Professional", None), ("Other", None),
]


def init_db(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    for name, parent in DEFAULT_CATEGORIES:
        conn.execute("INSERT OR IGNORE INTO categories (name, parent_category) VALUES (?, ?)", (name, parent))
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# PDF parsing — word-position based
# ---------------------------------------------------------------------------

_TX_LINE_RE = re.compile(r'^(\d{2})-(\d{2})\s+([a-z]{2})\s+(.+)$')
_AMT_RE = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{2}$')
_IBAN_RE = re.compile(r'[A-Z]{2}\d{2}\s+[A-Z]{4}\s+\d{4}\s+\d{4}\s+\d{2}')
_PERIOD_RE = re.compile(r'(\d{2})-(\d{2})-(\d{4})\s+[\d.,]+\s+CR')
_STMT_DATE_RE = re.compile(r'(\d{2})-(\d{2})-(\d{4})\s+\d{4}\s+\d{4}')
_DEBIT_X_THRESHOLD = 500


def parse_dutch_amount(s):
    return float(s.strip().replace(".", "").replace(",", "."))


def _extract_period(pdf):
    text = pdf.pages[0].extract_text() or ""
    lines = text.splitlines()
    new_month, new_year = None, None
    for i, line in enumerate(lines):
        if 'Nieuwsaldo' in line or 'Nieuwafschrift' in line:
            for j in range(i, min(i + 3, len(lines))):
                m = _PERIOD_RE.search(lines[j])
                if m:
                    new_month, new_year = int(m.group(2)), int(m.group(3))
                    break
    if new_year is None:
        for line in lines:
            m = _STMT_DATE_RE.search(line)
            if m:
                new_month, new_year = int(m.group(2)), int(m.group(3))
                # Statement date is 1 month after the period
                new_month -= 1
                if new_month == 0:
                    new_month = 12
                    new_year -= 1
                break
    if new_year is None:
        new_year, new_month = datetime.now().year, datetime.now().month
    return new_month, new_year


def _group_words_into_lines(words, tolerance=3):
    """Group words by y-coordinate into text lines."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w['top'], w['x0']))
    lines = []
    current_line = [sorted_words[0]]
    for w in sorted_words[1:]:
        if abs(w['top'] - current_line[0]['top']) <= tolerance:
            current_line.append(w)
        else:
            lines.append(current_line)
            current_line = [w]
    lines.append(current_line)
    return lines


def parse_pdf(pdf_path):
    """Extract transactions using word-level position data."""
    transactions = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        period_month, period_year = _extract_period(pdf)

        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue

            word_lines = _group_words_into_lines(words)

            # Process each line
            current_tx = None
            current_desc_parts = []

            for wline in word_lines:
                # Reconstruct text
                line_text = ' '.join(w['text'] for w in wline)
                m = _TX_LINE_RE.match(line_text)

                if m:
                    # Save previous tx
                    if current_tx is not None:
                        current_tx['description'] = ' '.join(current_desc_parts).strip()
                        transactions.append(current_tx)

                    day_s, month_s, code, rest = m.group(1), m.group(2), m.group(3), m.group(4)
                    tx_month = int(month_s)

                    # Resolve year
                    if period_month <= 1 and tx_month == 12:
                        tx_year = period_year - 1
                    elif tx_month > period_month + 1:
                        tx_year = period_year - 1
                    else:
                        tx_year = period_year
                    date_str = f"{tx_year}-{month_s}-{day_s}"

                    # Find amount word: rightmost amount-like word in this line
                    amt_word = None
                    for w in reversed(wline):
                        if _AMT_RE.match(w['text']) and w['x0'] > 400:
                            amt_word = w
                            break

                    if amt_word is None:
                        current_tx = None
                        current_desc_parts = []
                        continue

                    raw_amount = parse_dutch_amount(amt_word['text'])
                    is_credit = amt_word['x0'] >= _DEBIT_X_THRESHOLD
                    amount = raw_amount if is_credit else -raw_amount

                    # Extract IBAN and counterparty from rest
                    iban_match = _IBAN_RE.match(rest)
                    iban = None
                    cp_text = rest
                    if iban_match:
                        iban = iban_match.group(0).replace(' ', '')
                        cp_text = rest[iban_match.end():].strip()

                    # Remove trailing amount from counterparty
                    cp_parts = cp_text.rsplit(None, 1)
                    if len(cp_parts) == 2 and _AMT_RE.match(cp_parts[1]):
                        counterparty = cp_parts[0].strip()
                    elif len(cp_parts) == 1 and _AMT_RE.match(cp_parts[0]):
                        counterparty = ""
                    else:
                        counterparty = cp_text.strip()

                    current_tx = {
                        'date': date_str,
                        'amount': amount,
                        'counterparty': counterparty,
                        'iban': iban,
                        'raw_text': line_text,
                        'code': code,
                    }
                    current_desc_parts = []

                elif current_tx is not None:
                    # Skip metadata lines
                    if any(kw in line_text for kw in [
                        'Kenmerk machtiging', 'Transactiereferentie:',
                        '*=laatsteblad', 'CR=tegoed', 'D=tekort',
                        'IBANRekeningnummer', 'Rente Code', 'Datumafschrift',
                        'Vorigafschrift', 'Nieuwafschrift', 'Vorigsaldo', 'Nieuwsaldo',
                        'Bankcode', 'Rekeningafschrift', 'RaboDirectRekening',
                        'Postbus', 'BIC RABO',
                    ]):
                        continue
                    # Skip pure reference codes
                    clean = line_text.strip()
                    if re.match(r'^[A-Za-z0-9/_-]+$', clean) and len(clean) > 10:
                        continue
                    current_desc_parts.append(clean)

            # Last transaction on page
            if current_tx is not None:
                current_tx['description'] = ' '.join(current_desc_parts).strip()
                transactions.append(current_tx)

    return transactions


# ---------------------------------------------------------------------------
# Credit card PDF parsing (Rabobank Mastercard / GoldCard)
# ---------------------------------------------------------------------------

_CC_TX_RE = re.compile(r'^(\d{2})-(\d{2})-(\d{4})\s+(.+?)\s+(-?\s*[\d.]+,\d{2})$')
_CC_SKIP_DESC = re.compile(r'verrekening\s+vorig\s+overzicht', re.IGNORECASE)
_CC_TOKEN_TAIL = re.compile(r'\s+(?:Apple\s+Pay\s+)?Token:.*$', re.IGNORECASE)


def parse_cc_pdf(pdf_path):
    """Parse Rabobank credit card statement PDFs into transactions.

    Each line: DD-MM-YYYY <description> [USD <fx>] -<EUR amount>
    "Verrekening vorig overzicht" entries are skipped (previous balance).
    Koersopslag entries are kept (FX markup fee).
    """
    transactions = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                m = _CC_TX_RE.match(line)
                if not m:
                    continue
                day, mon, yr, desc, amt = m.groups()
                desc_clean = _CC_TOKEN_TAIL.sub("", desc).strip()
                if _CC_SKIP_DESC.search(desc_clean):
                    continue
                date_str = f"{yr}-{mon}-{day}"
                amount = parse_dutch_amount(amt.replace(" ", ""))
                # Sign: lines with "-" before amount are debits
                if "-" in amt:
                    amount = -abs(amount)
                else:
                    amount = abs(amount)
                transactions.append({
                    "date": date_str,
                    "amount": amount,
                    "counterparty": desc_clean,
                    "iban": None,
                    "raw_text": line,
                    "code": "cc",
                })
    # Add empty description (CC has it all in counterparty)
    for t in transactions:
        t["description"] = ""
    return transactions


# ---------------------------------------------------------------------------
# Auto-categorization
# ---------------------------------------------------------------------------

# Populate per-category keyword lists with patterns from your own statements.
# The structure is: (regex_pattern, "Category"). Each rule is tried in order;
# first match wins. Regex is case-insensitive.
#
# Guidelines:
#   - Keep generic chain/brand names that apply to any Dutch household.
#   - Remove patterns that contain your employer name, family member names,
#     or addresses (those are personal and won't match anyone else's statements).
#   - For Salary: add your own employer's identifier from your statements.
#   - For Transfer: add your own account-holder initials or payment references.
CATEGORY_RULES = [
    # Salary — populate with your employer's identifier as it appears on statements.
    # Example: (r"my employer name|salary ref", "Salary"),
    # "Salary": [],  # populate with your employer's identifier
    # Renovation (capex — large one-offs from contractors/architects). Must come before Shopping/Dining.
    (r"aannemer|bouwbedrijf|architect", "Renovation"),  # populate with your contractor names
    # Solar loan (paid via Buckaroo or similar intermediary). Must come before generic Transfer.
    (r"stichting\s+derdengelden\s+buckaroo", "Solar loan"),
    # Cash withdrawal (Geldmaat ATMs and Rabobank cash fees)
    (r"geldmaat", "Cash withdrawal"),
    # Remittances (international money transfer services)
    (r"remitly|\bxoom\b|wise\s+payments|transferwise|western\s+union|moneygram", "Remittances"),
    # Government (immigration, fines)
    (r"immigratie\s+en\s+naturalisatie|\bind\b\s+leges|cjib|verkeersboet|\brdw\b", "Government"),
    # Home maintenance (DIY stores, plumbing, garden — NL chains)
    (r"hornbach|praxis|gamma|karwei|intratuin|rioolspecialist|de-rioolspecialist", "Home maintenance"),
    # Energy (gas/electricity providers — NL)
    (r"\bengie\b|eneco|vattenfall|greenchoice|essent|energiedirect|\benergie\b", "Energy"),
    # Mortgage / loan (Rabobank-specific patterns — adapt for your bank)
    (r"rabobank\s*hypotheek|hypotheek|rabobank\s+regio.*incasso\s+inzake|\bfreo\b|rente\s*\+\s*aflossing\s+lening|saldo\s+lening|rabo\s+direct\s+financiering", "Mortgage"),
    # Healthcare (Dutch insurers + generic pharmacy/GP terms)
    (r"zilver.?n?\s*kruis|zorgverzekering|menzis|\bvgz\b|\bunive\b|huisarts|apotheek|tandarts|fysiotherap|medipoint|infomedics|holland\s+and\s+barrett|holland.*barrett|drogist|drogisterij", "Healthcare"),
    # Kids (baby/toy stores; must come before Shopping)
    (r"baby[-\s]?dump|prenatal|intertoys|babypark|mijn\s+kraamshop|baby.s\s+corner|scapino|smyths\s+toys|\blego\b|bart\s+smit|toys.?xl|korfbalvereniging|schoolfoto|\bschool\b\s+\w*\s*foto|fitkids|jeugdzorg", "Kids"),
    # Dining (restaurants, cafés, takeaway — generic chains; remove local-only entries)
    (r"thuisbezorgd|uber\s*eats|deliveroo|restaurant|eetcafe|eetcafé|\bcafe\b|café|mc\s*donalds|burger\s*king|subway|dominos|pizza|kfc|starbucks|febo|bedrijfsrest|bck\*mc|snackbar|new\s+york\s+pizza|la\s+place|wok\s+to\s+walk|sumo\s+restaurant|vishandel|fro\s*yo|frozen\s+yog|edeka\s+zurheide|hoog\s+catharijne|multisafepay|sitedish", "Dining"),
    # Groceries (Dutch chains + Asian specialty)
    (r"albert\s*heijn|\bah\s+\w|ah\s+to\s+go|jumbo|lidl|aldi|\bplus\b|ekoplaza|picnic|amazing\s+oriental|spar\s+university", "Groceries"),
    # Travel (hotels, flights, tourism, foreign travel — distinct from daily Transport)
    (r"booking\.com|airbnb|expedia|trip\.com|marriott|hilton|hyatt|sporthotel|hostel|sofitel|ibis\s+hotel|novotel|courtyard|airalo|schiphol|alp\*|wechat\s*pay|\balipay\b|china\s+southern|china\s+eastern|air\s+china|cathay\s+pacific|emirates|qatar\s+airways|singapore\s+airlines|ana\s+all\s+nippon|jal\b|turkish\s+airlines|swissair|ticketcounter|worldpay|\bsncf\b|deutsche\s+bahn|\beurostar\b|ryanair|easyjet|transavia|lufthansa|airfrance|wizz\s+air|carrefour|monoprix|boulangerie|airtrade|italiarail|huttopia|premc", "Travel"),
    # Transport (broad: trains, fuel, parking, vehicle service)
    (r"ns\.nl|ns\s+reizigers|ns\s+groep|ov-chipkaart|ovpay|\bshell\b|\bbp\b|\btotal\b|\besso\b|parkeer|q[\s-]?park|anwb|tinq|tango|tamoil|\bklm\b|ease2pay|kwik[\s-]?fit|q8\s+\d|freie\s+service|sanef|service\s+navigo|fietsvoordeel|fietsenwinkel|swapfiets|ns\s+fiets|fietsenstall", "Transport"),
    # Professional dues, conferences, scientific society memberships
    (r"microscopy\s+society|\brsc\b\s+royal|\bacs\b\s+pubs|elsevier|springer|wiley|nature\s+publishing|conference\s+fee|registration\s+fee", "Professional"),
    # AI/Dev subscriptions (Anthropic, Claude.AI, GitHub, OpenAI)
    (r"anthropic|claude\.ai|openai|chatgpt|github\b|gitlab|cursor\.com", "Subscriptions"),
    # Subscriptions (digital + media + app stores via PayPal)
    (r"netflix|spotify|apple\.com|google\s+storage|youtube|disney|\bhbo\b|de\s+volkskrant|\bnrc\b|telegraaf|dropbox|dpg\s+media|^rabobank$|paypal\s*\*itunes|paypal\s*\*google|playstation|nintendo|google\*google|kindle\s+svcs|musicnotes|\bring\s+standard|ring\s+plan|ring\s+yearly\s+plan|adobe|microsoft.*subscript|microsoft\*ultimate|patreon\*?\s*membership|\bamznprime\b|\bzwift\b|paypal\s*\*microsoft", "Subscriptions"),
    # Shopping (general retail, electronics, foreign online, clothing)
    (r"bol\.com|amazon|coolblue|mediamarkt|ikea|action|hema|blokker|primark|zara|h&m|bijenkorf|decathlon|goossens\s+wonen|paypal|uniqlo|c&a\s|c&a$|joybuy|fietsgoedkoper|kruidvat|etos|clarins|maxi\s+zoo|zooplus|dekbed[-\s]?discount|philips\s+domestic|amzn\s+mktp|amzn\s*mktp|amazonretail|\bbol\.com\b|wehkamp|otto\s+nl|\bvinted\b|\bmarktplaats\b|\bzalando\b|boekhandel|bristol\s+nederland|aliexpress", "Shopping"),
    # Municipal taxes (but NOT toeslagen — those are Other income)
    (r"gemeente|\bozb\b|waterschapsbelasting|afvalstoffenheffing|belastingen\s+jaar", "Municipal taxes"),
    # Tax authority payments (NOT toeslagen)
    (r"belastingdienst(?!.*toesl)(?!.*kit)(?!.*kgb)(?!.*huurto)", "Municipal taxes"),
    # Insurance
    (r"interpolis|nationale.nederlanden|aegon|centraal\s*beheer|verzekering|rheinland|allianz|unigarant", "Insurance"),
    # Other income (benefits, toeslagen)
    (r"sociale\s*verzekeringsbank|kinderbijslag|\bsvb\b|belastingdienst.*(toesl|kit|kgb|huurto)|zorgtoeslag|huurtoeslag|kindgebonden", "Other income"),
    # Childcare
    (r"kinderdagverblijf|\bbso\b|kinderopvang|\bcreche\b|cr[eè]che|korein|partou|smallsteps", "Childcare"),
    (r"hellofresh", "Groceries"),
    # Water
    (r"vitens|brabant\s+water|waterbedrijf", "Water"),
    # Internet / telecom
    (r"\bkpn\b|\bziggo\b|t-mobile|vodafone|\btele2\b", "Internet"),
    # Savings
    (r"spaarrekening|savings|depositobank", "Savings"),
    # Charity
    (r"unicef|vluchteling|rode\s+kruis|oxfam|artsen\s+zonder|greenpeace|wwf|amnesty", "Charity"),
    # Banking fees (FX markup on credit card)
    (r"koersopslag|valutaopslag", "Banking fees"),
    # Credit card bill (monthly Rabobank NL aggregate of CC charges — real spending, but lumped)
    (r"rabobank\s+nederland|kaartnummer:\s*\*+\.\*+\.\*+\.\d+", "Credit card"),
    # Transfers (between own accounts and payment apps) — populate with your own initials/references
    # Example: (r"\bA\.\s*Smith\b|\btikkie\b|overboeking\s+naar\s+creditcard|...", "Transfer"),
    (r"\btikkie\b|overboeking\s+naar\s+creditcard|overboeking\s+saldo\s+van\s+creditcard|iban-creditcard|betaalverzoek\s+rabobank|rabo\s+betaalverzoek|abn\s+amro\s+bank|betaalverzoek|via\s+ing\s+betaalverzoek|via\s+rabo\s+betaalverzo|\bing\s+bank\b\s+nv|knab\s+bank|bunq\s+bank|n26\s+bank", "Transfer"),  # add your own name patterns
    # Leisure (cinema, pool, library, family outings — NL chains/venues)
    (r"zwembad|bioscoop|pathe|vue\s+cinema|ballorig|biblioth|park\s+playground|bounce\s+valley|de\s+efteling|monkey\s+town", "Leisure"),
    # Transport (vehicle purchases and maintenance)
    (r"skoda|automotive|autobedrijf|my\s+tyre|bandenconcurren|skodawebshop", "Transport"),
    # Healthcare providers that do not use standard insurer keywords
    (r"maxima\s+mc", "Healthcare"),
]

_COMPILED_RULES = [(re.compile(p, re.IGNORECASE), c) for p, c in CATEGORY_RULES]


INCOME_CATEGORIES = {"Salary", "Other income"}


def categorize(counterparty, description="", amount=None):
    text = f"{counterparty} {description}"
    for pattern, category in _COMPILED_RULES:
        if pattern.search(text):
            # Income categories only valid for credits (positive amounts)
            if amount is not None and amount < 0 and category in INCOME_CATEGORIES:
                continue
            return category
    return "Other"


def insert_transactions(conn, transactions, source_file):
    inserted = 0
    for tx in transactions:
        cp = tx.get("counterparty", "") or ""
        desc = tx.get("description", "") or ""
        category = categorize(cp, desc, tx["amount"])
        try:
            conn.execute(
                """INSERT INTO transactions
                    (date, amount, counterparty, description, category,
                     iban_to, balance_after, raw_text, source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tx["date"], tx["amount"], cp, desc, category,
                 tx.get("iban"), tx.get("balance_after"),
                 tx.get("raw_text", ""), source_file))
            inserted += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return inserted


def recategorize_existing(conn):
    updated = 0
    rows = conn.execute(
        "SELECT id, counterparty, description, amount, category FROM transactions"
    ).fetchall()
    for tx_id, counterparty, description, amount, category in rows:
        new_category = categorize(counterparty or "", description or "", amount)
        if new_category != category:
            conn.execute(
                "UPDATE transactions SET category = ? WHERE id = ?",
                (new_category, tx_id),
            )
            updated += 1
    conn.commit()
    return updated


def import_folder(conn, drop_folder=None):
    folder = Path(drop_folder) if drop_folder else DROP_FOLDER
    result = {
        "files_processed": 0,
        "files_skipped": 0,
        "files_ignored": 0,
        "rows_recategorized": 0,
        "total_transactions": 0,
        "errors": [],
    }
    already = {r[0] for r in conn.execute("SELECT filename FROM import_log").fetchall()}

    for pdf_path in sorted(Path(folder).glob("*.pdf")):
        fn = pdf_path.name
        if not STATEMENT_FILE_RE.match(fn):
            result["files_ignored"] += 1
            continue
        # Skip Chrome duplicate downloads
        if re.search(r'\(\d+\)', fn):
            result["files_skipped"] += 1
            continue
        if fn in already:
            result["files_skipped"] += 1
            continue
        try:
            if fn.lower().startswith("creditcard"):
                txs = parse_cc_pdf(pdf_path)
            else:
                txs = parse_pdf(pdf_path)
            count = insert_transactions(conn, txs, fn)
            dates = [t["date"] for t in txs] if txs else []
            dr = f"{min(dates)} to {max(dates)}" if dates else None
            conn.execute("INSERT INTO import_log (filename, row_count, date_range) VALUES (?,?,?)", (fn, count, dr))
            conn.commit()
            result["files_processed"] += 1
            result["total_transactions"] += count
        except Exception as exc:
            result["errors"].append({"file": fn, "error": str(exc)})
    result["rows_recategorized"] = recategorize_existing(conn)
    return result


def query_monthly_summary(conn, year, month):
    ms = f"{year:04d}-{month:02d}"
    rows = conn.execute("SELECT amount, category FROM transactions WHERE date LIKE ?", (f"{ms}-%",)).fetchall()
    inc = sum(r[0] for r in rows if r[0] > 0)
    exp = sum(r[0] for r in rows if r[0] < 0)
    cats = conn.execute("SELECT category, SUM(amount), COUNT(*) FROM transactions WHERE date LIKE ? GROUP BY category ORDER BY SUM(amount)", (f"{ms}-%",)).fetchall()
    return {"total_income": round(inc, 2), "total_expense": round(exp, 2), "net": round(inc + exp, 2),
            "by_category": [(r[0], round(r[1], 2), r[2]) for r in cats]}


def query_recurring_bills(conn):
    rows = conn.execute(
        """SELECT counterparty, category, AVG(amount), COUNT(*), MAX(date)
        FROM transactions WHERE amount < 0
        GROUP BY counterparty HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC, counterparty""").fetchall()
    return [{"counterparty": r[0], "category": r[1], "avg_amount": round(r[2], 2),
             "occurrences": r[3], "last_seen": r[4]} for r in rows]


def main():
    ap = argparse.ArgumentParser(description="Import Rabobank PDF statements")
    ap.add_argument("--drop-folder", type=Path, default=DROP_FOLDER)
    ap.add_argument("--db-path", type=Path, default=DB_PATH)
    args = ap.parse_args()
    conn = init_db(db_path=args.db_path)
    s = import_folder(conn, drop_folder=args.drop_folder)
    conn.close()
    print(f"Files processed : {s['files_processed']}")
    print(f"Files skipped   : {s['files_skipped']}")
    print(f"Files ignored   : {s['files_ignored']}")
    print(f"Transactions    : {s['total_transactions']}")
    print(f"Recategorized   : {s['rows_recategorized']}")
    if s["errors"]:
        print(f"Errors          : {len(s['errors'])}")
        for e in s["errors"]:
            print(f"  {e['file']}: {e['error']}")


if __name__ == "__main__":
    main()
