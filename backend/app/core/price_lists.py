"""Verified, versioned price-list index derived from Docling table cells."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
import unicodedata

from app.config import DATA_DIR

PRICE_DB = DATA_DIR / "structured_prices.sqlite"
_lock = RLock()

_PRICE_HEADER = re.compile(r"\b(prezz[oi]|prices?|import[oi]|tariff[ae]|cost[oi]?|eur(?:o)?|usd|gbp)\b|[€$£]", re.I)
_CODE_HEADER = re.compile(r"\b(codice|cod\.?|code|sku|articolo|art\.?|id)\b", re.I)
_DESCRIPTION_HEADER = re.compile(r"\b(descrizione|descr\.?|description|prodotto|servizio|denominazione|voce)\b", re.I)
_UNIT_HEADER = re.compile(r"\b(unità|unita|unit|u\.?m\.?|misura)\b", re.I)
_PRICE_INTENT = re.compile(r"\b(prezz\w*|cost\w*|import[oi]\w*|tariff\w*|listin\w*|quanto\s+costa|€|eur|euro)\b", re.I)
_COUNT_INTENT = re.compile(r"\b(quanti|quante|conteggio|conta|numero\s+di)\b", re.I)
_COMPARE_INTENT = re.compile(r"\b(confront\w*|differenz\w*|variaz\w*|rispetto|aument\w*|diminuit\w*)\b", re.I)
_STATS_INTENT = re.compile(r"\b(media|medio|minim\w*|massim\w*)\b", re.I)

_STOPWORDS = {
    "a", "al", "alla", "alle", "anche", "che", "con", "costa", "costo", "da", "dal", "dalla",
    "dei", "del", "della", "delle", "di", "e", "euro", "eur", "fra", "gli", "i", "il", "in",
    "la", "le", "listino", "listini", "lo", "mi", "nel", "nella", "o", "per", "prezzo", "prezzi",
    "prodotto", "prodotti", "quanto", "qual", "quale", "quali", "quanti", "quante", "rispetto", "tra", "un",
    "una", "versione", "versioni", "voce", "voci", "conta", "conteggio", "numero", "mostra", "dammi",
    "confronta", "confronto", "differenza", "variazione", "media", "medio", "minimo", "massimo",
    "meno", "piu", "sotto", "sopra", "inferiore", "superiore", "almeno", "fino",
    "codice", "cod", "sku", "anno", "rev", "revisione", "ver", "uguale", "ed",
}


def _connect() -> sqlite3.Connection:
    PRICE_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(PRICE_DB, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma journal_mode=wal")
    connection.execute("pragma foreign_keys=on")
    connection.executescript("""
        create table if not exists price_list_versions (
          document_id text primary key,
          knowledge_id text not null,
          filename text not null,
          series_key text not null,
          version_label text not null,
          effective_date text,
          content_hash text not null,
          indexed_at text not null
        );
        create index if not exists price_versions_kb_series
          on price_list_versions(knowledge_id, series_key, effective_date, version_label);
        create table if not exists price_list_entries (
          document_id text not null references price_list_versions(document_id) on delete cascade,
          table_ref text not null,
          row_index integer not null,
          price_column_index integer not null,
          price_column text not null,
          item_code text,
          description text,
          unit text,
          currency text,
          price_value text not null,
          raw_price text not null,
          raw_cells text not null,
          headers text not null,
          page_start integer,
          page_end integer,
          source_regions text not null,
          primary key(document_id, table_ref, row_index, price_column_index)
        );
        create index if not exists price_entries_document on price_list_entries(document_id);
        create index if not exists price_entries_code on price_list_entries(item_code);
    """)
    return connection


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _plain(text)).strip()


def _version_metadata(filename: str) -> tuple[str, str, str | None]:
    stem = Path(filename).stem.strip()
    full_date = re.search(r"(?<!\d)(20\d{2})[-_.](0?[1-9]|1[0-2])[-_.](0?[1-9]|[12]\d|3[01])(?!\d)", stem)
    italian_date = re.search(r"(?<!\d)(0?[1-9]|[12]\d|3[01])[-_.](0?[1-9]|1[0-2])[-_.](20\d{2})(?!\d)", stem)
    revision = re.search(r"(?i)(?:^|[-_.\s])(v(?:er(?:sione)?)?\s*\d+(?:\.\d+)*|rev(?:isione)?\s*\d+)(?:$|[-_.\s])", stem)
    year = re.search(r"(?<!\d)(20\d{2})(?!\d)", stem)
    effective_date = None
    version_label = stem
    remove_spans = []
    if full_date:
        y, m, d = full_date.groups()
        effective_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        version_label = effective_date
        remove_spans.append(full_date.span())
    elif italian_date:
        d, m, y = italian_date.groups()
        effective_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        version_label = effective_date
        remove_spans.append(italian_date.span())
    elif revision:
        version_label = re.sub(r"\s+", "", revision.group(1)).upper()
        remove_spans.append(revision.span(1))
    elif year:
        version_label = year.group(1)
        remove_spans.append(year.span())

    series_text = stem
    for start, end in reversed(remove_spans):
        series_text = series_text[:start] + " " + series_text[end:]
    series_key = _key(series_text) or _key(stem)
    return series_key, version_label, effective_date


def _currencies(*values: str) -> set[str]:
    text = " ".join(values).upper()
    currencies = set()
    if re.search(r"\b(?:EUR|EURO)\b|€", text):
        currencies.add("EUR")
    if re.search(r"\bUSD\b|\$", text):
        currencies.add("USD")
    if re.search(r"\bGBP\b|£", text):
        currencies.add("GBP")
    return currencies


def parse_decimal(raw: str) -> Decimal | None:
    """Parse an explicit numeric cell without inventing missing values."""
    value = raw.strip().replace("\u00a0", " ")
    value = re.sub(r"(?i)\b(?:EUR|EURO|USD|GBP)\b|[€$£]", "", value).strip()
    if not re.fullmatch(r"[-+]?\s*\d[\d .,'’]*", value):
        return None
    value = value.replace(" ", "").replace("'", "").replace("’", "")
    sign = ""
    if value[:1] in "+-":
        sign, value = value[0], value[1:]
    if not value or not any(char.isdigit() for char in value):
        return None
    if "," in value and "." in value:
        decimal_sep = "," if value.rfind(",") > value.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        integer, fraction = value.rsplit(decimal_sep, 1)
        if not re.fullmatch(rf"\d{{1,3}}(?:\{thousands_sep}\d{{3}})+", integer) or not fraction.isdigit():
            return None
        value = value.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in value or "." in value:
        separator = "," if "," in value else "."
        parts = value.split(separator)
        if len(parts) == 2:
            # 1.234 / 1,234 can mean either 1234 or 1.234; do not guess.
            if len(parts[-1]) == 3 or not parts[-1].isdigit():
                return None
            value = ".".join(parts)
        elif re.fullmatch(rf"\d{{1,3}}(?:\{separator}\d{{3}})+", value):
            value = "".join(parts)
        else:
            return None
    try:
        return Decimal(sign + value)
    except InvalidOperation:
        return None


def _headers(block: dict) -> list[str]:
    rows = [row for row in block.get("rows", []) if row.get("is_header")]
    width = max((len(row.get("cells", [])) for row in block.get("rows", [])), default=0)
    headers = []
    for column in range(width):
        parts = [str(row.get("cells", [])[column]).strip() for row in rows if column < len(row.get("cells", [])) and str(row.get("cells", [])[column]).strip()]
        headers.append(" / ".join(dict.fromkeys(parts)) or f"Colonna {column + 1}")
    return headers


def _column(headers: list[str], pattern: re.Pattern) -> int | None:
    return next((index for index, header in enumerate(headers) if pattern.search(header)), None)


def _table_entries(block: dict) -> list[dict]:
    headers = _headers(block)
    if not headers:
        return []
    price_columns = [(index, header) for index, header in enumerate(headers) if _PRICE_HEADER.search(header)]
    if not price_columns:
        return []
    code_column = _column(headers, _CODE_HEADER)
    description_column = _column(headers, _DESCRIPTION_HEADER)
    unit_column = _column(headers, _UNIT_HEADER)
    regions = block.get("source_regions") or []
    pages = [int(region["page"]) for region in regions if region.get("page") is not None]
    output = []
    for row in block.get("rows", []):
        if row.get("is_header"):
            continue
        cells = [str(cell).strip() for cell in row.get("cells", [])]
        padded = cells + [""] * (len(headers) - len(cells))
        raw_cells = {f"{index}:{headers[index]}": padded[index] for index in range(len(headers))}
        for price_index, price_header in price_columns:
            raw_price = padded[price_index]
            price = parse_decimal(raw_price)
            if price is None:
                continue
            currencies = _currencies(price_header, raw_price)
            if len(currencies) > 1:
                continue
            excluded = {index for index, _ in price_columns}
            if code_column is not None:
                excluded.add(code_column)
            if unit_column is not None:
                excluded.add(unit_column)
            description = padded[description_column] if description_column is not None else " ".join(
                cell for index, cell in enumerate(padded) if index not in excluded and cell
            )
            output.append({
                "table_ref": block.get("id", ""),
                "row_index": int(row.get("row_index", 0)),
                "price_column_index": price_index,
                "price_column": price_header,
                "item_code": padded[code_column] if code_column is not None else None,
                "description": description or None,
                "unit": padded[unit_column] if unit_column is not None else None,
                "currency": next(iter(currencies), None),
                "price_value": format(price, "f"),
                "raw_price": raw_price,
                "raw_cells": raw_cells,
                "headers": headers,
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "source_regions": regions,
            })
    return output


def index_price_document(structure: dict, knowledge_id: str, document_id: str, filename: str) -> int:
    """Atomically replace the derived price index for one document."""
    tables = [block for block in structure.get("blocks", []) if block.get("kind") == "table"]
    entries = [entry for table in tables for entry in _table_entries(table)]
    digest = sha256(json.dumps(tables, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    series_key, version_label, effective_date = _version_metadata(filename)
    with _lock, _connect() as connection:
        connection.execute("begin immediate")
        connection.execute("delete from price_list_versions where document_id=?", (document_id,))
        if entries:
            connection.execute(
                "insert into price_list_versions values(?,?,?,?,?,?,?,?)",
                (document_id, knowledge_id, filename, series_key, version_label, effective_date, digest,
                 datetime.now(timezone.utc).isoformat()),
            )
            connection.executemany("""
                insert into price_list_entries(
                  document_id,table_ref,row_index,price_column_index,price_column,item_code,description,unit,
                  currency,price_value,raw_price,raw_cells,headers,page_start,page_end,source_regions
                ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [(
                document_id, entry["table_ref"], entry["row_index"], entry["price_column_index"],
                entry["price_column"], entry["item_code"], entry["description"], entry["unit"],
                entry["currency"], entry["price_value"], entry["raw_price"],
                json.dumps(entry["raw_cells"], ensure_ascii=False), json.dumps(entry["headers"], ensure_ascii=False),
                entry["page_start"], entry["page_end"], json.dumps(entry["source_regions"], ensure_ascii=False),
            ) for entry in entries])
        connection.commit()
    return len(entries)


def delete_price_document(document_id: str) -> None:
    with _lock, _connect() as connection:
        connection.execute("delete from price_list_versions where document_id=?", (document_id,))


def delete_price_knowledge(knowledge_id: str) -> None:
    with _lock, _connect() as connection:
        connection.execute("delete from price_list_versions where knowledge_id=?", (knowledge_id,))


@dataclass(frozen=True)
class PricePlan:
    intent: str
    terms: tuple[str, ...]
    codes: tuple[str, ...]
    versions: tuple[str, ...]
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True


def plan_price_question(question: str, *, require_intent: bool = True) -> PricePlan | None:
    has_intent = bool(_PRICE_INTENT.search(question) or _COUNT_INTENT.search(question) or _COMPARE_INTENT.search(question) or _STATS_INTENT.search(question))
    if require_intent and not has_intent:
        return None
    normalized = _plain(question)
    if _COMPARE_INTENT.search(question):
        version_candidates = re.findall(r"(?<!\d)20\d{2}(?!\d)", normalized)
    else:
        version_candidates = re.findall(r"(?:anno|nel|del|versione|listino)\s+(20\d{2})(?!\d)", normalized)
    versions = tuple(dict.fromkeys(version_candidates))
    full_dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", normalized)
    revisions = re.findall(r"\b(?:v(?:er(?:sione)?)?|rev(?:isione)?)\s*\d+(?:\.\d+)*\b", normalized)
    if full_dates or revisions:
        versions = tuple(dict.fromkeys(full_dates + [re.sub(r"\s+", "", value) for value in revisions]))
    code_candidates = re.findall(r"\b(?=[A-Za-z0-9./_-]*\d)[A-Za-z0-9]+(?:[./_-][A-Za-z0-9]+)+\b", question)
    code_candidates += re.findall(r"\b(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+\b", question)
    code_candidates += re.findall(r"(?i)\b(?:codice|cod\.?|sku|articolo|art\.?)\s+([0-9]+)\b", question)
    codes = tuple(dict.fromkeys(token.casefold() for token in code_candidates
                                if token.casefold() not in versions))
    minimum = maximum = None
    number = r"([-+]?\d[\d .]*(?:[,.]\d+)?)"
    below = re.search(rf"(?:meno\s+di|sotto|inferiore\s+a|fino\s+a)\s*{number}", normalized)
    above = re.search(rf"(?:piu\s+di|sopra|superiore\s+a|almeno)\s*{number}", normalized)
    between = re.search(rf"(?:tra|da)\s*{number}\s*(?:e|a)\s*{number}", normalized)
    if between:
        between_min, between_max = parse_decimal(between.group(1)), parse_decimal(between.group(2))
        if between_min is None or between_max is None:
            return None
        if not (between_min and between_max and 1900 <= between_min <= 2100 and 1900 <= between_max <= 2100):
            minimum, maximum = between_min, between_max
    else:
        maximum = parse_decimal(below.group(1)) if below else None
        minimum = parse_decimal(above.group(1)) if above else None
        if (below and maximum is None) or (above and minimum is None):
            return None

    words = re.findall(r"[a-z0-9]+", normalized)
    numeric_values = set(versions)
    reference_words = set(re.findall(r"[a-z0-9]+", " ".join((*versions, *codes))))
    for value in (minimum, maximum):
        if value is not None:
            numeric_values.add(format(value, "f"))
    intent_prefixes = ("prezz", "cost", "listin", "confront", "differ", "variaz", "import", "tariff", "prodott", "articol", "cont", "quant", "minim", "massim")
    terms = tuple(dict.fromkeys(
        word for word in words
        if len(word) > 1 and word not in _STOPWORDS and word not in numeric_values and word not in reference_words
        and not re.fullmatch(r"\d+(?:[.,]\d+)?", word)
        and not word.startswith(intent_prefixes)
    ))
    intent = "compare" if _COMPARE_INTENT.search(question) else "count" if _COUNT_INTENT.search(question) else "stats" if _STATS_INTENT.search(question) else "lookup"
    return PricePlan(intent=intent, terms=terms, codes=codes, versions=versions, minimum=minimum, maximum=maximum,
                     minimum_inclusive=not bool(above and above.group(0).split()[0] in ("piu", "sopra", "superiore")),
                     maximum_inclusive=not bool(below and below.group(0).split()[0] in ("meno", "sotto", "inferiore")))


def _matches(row: dict, plan: PricePlan) -> bool:
    price = Decimal(row["price_value"])
    if plan.minimum is not None and price < plan.minimum:
        return False
    if plan.maximum is not None and price > plan.maximum:
        return False
    if plan.minimum is not None and not plan.minimum_inclusive and price == plan.minimum:
        return False
    if plan.maximum is not None and not plan.maximum_inclusive and price == plan.maximum:
        return False
    if plan.versions and not any(version == _plain(row['version_label']) or
                                (len(version) == 4 and version == str(row['effective_date'] or '')[:4])
                                for version in plan.versions):
        return False
    code = _key(row.get("item_code") or "")
    if plan.codes and not any(_key(candidate) == code for candidate in plan.codes):
        return False
    haystack = _key(" ".join(str(row.get(field) or "") for field in ("item_code", "description", "price_column")))
    return not plan.terms or all(term in haystack for term in plan.terms)


def _load_entries(knowledge_id: str) -> list[dict]:
    if not PRICE_DB.exists():
        return []
    with _lock, _connect() as connection:
        rows = connection.execute("""
            select e.*,v.knowledge_id,v.filename,v.series_key,v.version_label,v.effective_date,v.indexed_at
            from price_list_entries e join price_list_versions v using(document_id)
            where v.knowledge_id=?
            order by v.series_key,coalesce(v.effective_date,''),v.version_label,e.item_code,e.description,e.price_column
        """, (knowledge_id,)).fetchall()
    return [{**dict(row), "raw_cells": json.loads(row["raw_cells"]),
             "headers": json.loads(row["headers"]), "source_regions": json.loads(row["source_regions"])} for row in rows]


def _money(value: Decimal, currency: str | None) -> str:
    rendered = format(value.quantize(Decimal("0.01")), "f").replace(".", ",")
    return f"{rendered} {currency}" if currency else rendered


def _label(row: dict) -> str:
    return " — ".join(value for value in (row.get("item_code"), row.get("description")) if value) or "Riga di listino"


def _version_sort(row: dict) -> tuple:
    if row.get("effective_date"):
        return (0, row["effective_date"], (), row["indexed_at"])
    numbers = tuple(int(value) for value in re.findall(r"\d+", row.get("version_label") or ""))
    if len(numbers) == 1 and 1900 <= numbers[0] <= 2100:
        return (0, f"{numbers[0]:04d}-00-00", (), row["indexed_at"])
    return (1, "", numbers, row["indexed_at"])
def _source(row: dict, text: str | None = None) -> dict:
    return {
        "text": text or " | ".join(row["raw_cells"].values()),
        "filename": row["filename"],
        "document_id": row["document_id"],
        "chunk_index": row["row_index"],
        "page_start": row["page_start"] or 1,
        "page_end": row["page_end"] or row["page_start"] or 1,
        "section_path": [], "section_refs": [], "source_regions": row["source_regions"],
        "content_kind": "structured_price", "score": 1.0,
        "retrieval_method": "structured_price", "context_scope": "structured_row",
        "section_complete": True, "expanded_chunks": 1, "verified_data": True,
        "version_label": row["version_label"], "series_key": row["series_key"],
        "price_value": row["price_value"], "price_column": row["price_column"],
        "raw_cells": row["raw_cells"],
    }


def _lookup(rows: list[dict]) -> tuple[str, list[dict]]:
    shown = rows[:20]
    sources = [_source(row) for row in shown]
    lines = ["Ho trovato questi valori nelle righe strutturate dei listini:"]
    for index, row in enumerate(shown, 1):
        price = _money(Decimal(row["price_value"]), row["currency"])
        unit = f"/{row['unit']}" if row.get("unit") else ""
        lines.append(f"- **{_label(row)}**: {price}{unit} — {row['version_label']}, {row['price_column']} [{index}]")
    if len(rows) > len(shown):
        lines.append(f"\nSono mostrate 20 righe su {len(rows)} corrispondenti.")
    return "\n".join(lines), sources


def _count(rows: list[dict]) -> tuple[str, list[dict]]:
    distinct = {(row["document_id"], row["table_ref"], row["row_index"]) for row in rows}
    grouped: dict[str, set[tuple]] = {}
    representative = {}
    for row in rows:
        key = row["document_id"]
        grouped.setdefault(key, set()).add((row["table_ref"], row["row_index"]))
        representative[key] = row
    total_label = "riga di listino" if len(distinct) == 1 else "righe di listino"
    lines = [f"Il conteggio verificato è **{len(distinct)} {total_label}**."]
    sources = []
    for index, (key, items) in enumerate(grouped.items(), 1):
        row_label = "riga" if len(items) == 1 else "righe"
        row = representative[key]
        lines.append(f"- {row['filename']} — versione {row['version_label']}: **{len(items)}** {row_label} [{index}]")
        sources.append(_source(representative[key], text=f"Conteggio strutturato: {len(items)} {row_label} di listino"))
    return "\n".join(lines), sources


def _compare(rows: list[dict]) -> tuple[str, list[dict]] | None:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        item = _key(row.get("item_code") or row.get("description") or "")
        groups.setdefault((row["series_key"], item, row["price_column"], row["currency"], row["unit"]), []).append(row)
    comparisons = []
    for entries in groups.values():
        # Duplicate item rows within a version are ambiguous, even if prices agree.
        if len({entry["document_id"] for entry in entries}) != len(entries):
            continue
        if len({entry["version_label"] for entry in entries}) != len(entries):
            continue
        ordered = sorted(entries, key=_version_sort)
        if len(ordered) >= 2:
            comparisons.append((ordered[0], ordered[-1]))
    if not comparisons:
        return None
    lines = ["Confronto calcolato sui valori strutturati delle versioni:"]
    sources = []
    for old, new in comparisons[:20]:
        old_value, new_value = Decimal(old["price_value"]), Decimal(new["price_value"])
        delta = new_value - old_value
        percent = (delta / old_value * 100) if old_value else None
        first_ref, second_ref = len(sources) + 1, len(sources) + 2
        change = f"{_money(delta, new['currency'])}"
        if percent is not None:
            change += f" ({format(percent.quantize(Decimal('0.01')), 'f').replace('.', ',')}%)"
        lines.append(
            f"- **{_label(new)}**: {_money(old_value, old['currency'])} ({old['version_label']}) → "
            f"{_money(new_value, new['currency'])} ({new['version_label']}), variazione **{change}** [{first_ref}][{second_ref}]"
        )
        sources.extend([_source(old), _source(new)])
    return "\n".join(lines), sources


def _stats(rows: list[dict]) -> tuple[str, list[dict]]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["document_id"], row["price_column"], row["currency"], row["unit"]), []).append(row)
    lines = ["Statistiche calcolate sui valori strutturati:"]
    sources = []
    for (_, column, currency, unit), entries in grouped.items():
        values = [Decimal(entry["price_value"]) for entry in entries]
        minimum, maximum = min(values), max(values)
        average = sum(values) / len(values)
        lines.append(
            f"- {entries[0]['filename']} — {entries[0]['version_label']}, {column}"
            f"{f'/{unit}' if unit else ''}, {len(entries)} valori {currency or 'senza valuta indicata'}: minimo **{_money(minimum, currency)}**, "
            f"massimo **{_money(maximum, currency)}**, media **{_money(average, currency)}**."
        )
        for target in (minimum, maximum):
            row = next(entry for entry in entries if Decimal(entry["price_value"]) == target)
            sources.append(_source(row))
    return "\n".join(lines), sources


def query_price_lists(question: str, knowledge_id: str, *, current_question: str | None = None,
                      document_ids: set[str] | None = None) -> dict | None:
    plan = plan_price_question(question)
    if plan is None:
        return None
    if current_question and current_question != question:
        # A self-contained non-price question must not inherit a previous numeric intent.
        if not plan_price_question(current_question) and len(current_question.split()) > 4:
            return None
        current = plan_price_question(current_question, require_intent=False)
        if current:
            current_has_intent = bool(
                _PRICE_INTENT.search(current_question) or _COUNT_INTENT.search(current_question)
                or _COMPARE_INTENT.search(current_question) or _STATS_INTENT.search(current_question)
            )
            follow_up = bool(re.match(r"\s*(?:e\b|invece\b|nel\b|nella\b)", _plain(current_question)))
            inherits_target = current.intent in ("lookup", "compare") and not (current.codes or current.terms)
            if current_has_intent and not follow_up and not inherits_target:
                plan = current
            else:
                plan = replace(
                    plan,
                    intent=current.intent if current_has_intent else plan.intent,
                    terms=current.terms or plan.terms,
                    codes=current.codes or plan.codes,
                    versions=current.versions or plan.versions,
                    minimum=current.minimum if current.minimum is not None else plan.minimum,
                    maximum=current.maximum if current.maximum is not None else plan.maximum,
                    minimum_inclusive=current.minimum_inclusive if current.minimum is not None else plan.minimum_inclusive,
                    maximum_inclusive=current.maximum_inclusive if current.maximum is not None else plan.maximum_inclusive,
                )
    visible_rows = [row for row in _load_entries(knowledge_id)
                    if document_ids is None or row["document_id"] in document_ids]
    rows = [row for row in visible_rows if _matches(row, plan)]
    if not rows:
        if plan.intent == "count" and (plan.minimum is not None or plan.maximum is not None):
            population = [row for row in visible_rows if _matches(row, replace(plan, minimum=None, maximum=None))]
            if population:
                source_rows = {row["document_id"]: row for row in population}
                sources = [_source(row, text="Listino esaminato: nessuna riga soddisfa la soglia richiesta.")
                           for row in source_rows.values()]
                return {"answer": "Il conteggio verificato è **0 righe di listino** che soddisfano la soglia richiesta.",
                        "sources": sources, "rows_matched": 0, "intent": "count"}
        return None
    if plan.intent == "count":
        answer, sources = _count(rows)
    elif plan.intent == "compare":
        result = _compare(rows)
        if result is None:
            return None
        answer, sources = result
    elif plan.intent == "stats":
        answer, sources = _stats(rows)
    else:
        answer, sources = _lookup(rows)
    return {"answer": answer, "sources": sources, "rows_matched": len(rows), "intent": plan.intent}
