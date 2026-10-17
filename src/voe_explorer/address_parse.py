"""Parsing free-form addresses and VOE street names into comparable parts."""
from __future__ import annotations

import re

from .models import AddressQuery, StreetName

CANONICAL_KINDS = (
    "вулиця", "провулок", "проїзд", "проспект", "бульвар", "площа",
    "тупик", "узвіз", "шосе", "набережна", "майдан", "спуск",
)

# Extend freely: keys are lowercase without the trailing dot.
KIND_SYNONYMS: dict[str, str] = {k: k for k in CANONICAL_KINDS} | {
    "вул": "вулиця",
    "пров": "провулок", "пр-к": "провулок",
    "пр-д": "проїзд",
    "просп": "проспект", "пр-т": "проспект",
    "бул": "бульвар", "б-р": "бульвар",
    "пл": "площа",
    "туп": "тупик",
}

ORDINAL_WORDS: dict[str, int] = {}
for _n, _stem in enumerate(
    ("перш", "друг", "трет", "четверт", "п'ят", "шост", "сьом", "восьм", "дев'ят", "десят"), start=1
):
    for _end in ("ий", "ій", "а", "я", "е", "є"):
        ORDINAL_WORDS[_stem + _end] = _n

_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "`": "'", "‘": "'", "´": "'"})
_LATIN_TO_CYR = str.maketrans("ABCEHIKMOPTXY", "АВСЕНІКМОРТХУ")

_ORDINAL_TOKEN = re.compile(r"^(\d+)-?(й|ий|ій|а|я|е)$")
_HOUSE_TOKEN = re.compile(r"^\d+(/\d+)?(-?[а-щьюяієґa-z])?(/\d+)?$")


def _clean(text: str) -> str:
    text = text.translate(_APOSTROPHES).lower()
    text = re.sub(r"(\d)\s*/\s*(\d)", r"\1/\2", text)
    return re.sub(r"\s+", " ", text).strip()


def _kind_of(token: str) -> str | None:
    return KIND_SYNONYMS.get(token.rstrip("."))


def _ordinal_of(token: str) -> int | None:
    m = _ORDINAL_TOKEN.match(token)
    if m:
        return int(m.group(1))
    return ORDINAL_WORDS.get(token)


def normalize_house(text: str) -> str:
    s = re.sub(r"\s+", "", text.translate(_APOSTROPHES)).upper().translate(_LATIN_TO_CYR)
    return re.sub(r"(\d)-(\D)", r"\1\2", s)


def _split_street(tokens: list[str]) -> StreetName:
    kind = ordinal = None
    name: list[str] = []
    for tok in tokens:
        tok = tok.strip(",")
        if not tok or tok == "*":
            continue
        if kind is None and _kind_of(tok):
            kind = _kind_of(tok)
        elif ordinal is None and _ordinal_of(tok) is not None:
            ordinal = _ordinal_of(tok)
        elif ordinal is None and not name and tok.isdigit():
            ordinal = int(tok)
        else:
            name.append(tok)
    return StreetName(kind, ordinal, " ".join(name))


def parse_query(text: str) -> AddressQuery:
    s = _clean(text)
    house = None
    if "," in s:
        head, tail = s.rsplit(",", 1)
        if _HOUSE_TOKEN.match(tail.strip().replace(" ", "")):
            s, house = head, tail.strip()
    tokens = s.split()
    # "12 а" -> "12а"
    if house is None and len(tokens) >= 2 and tokens[-2].isdigit() and re.fullmatch(r"[а-щьюяієґa-z]", tokens[-1]):
        tokens[-2:] = [tokens[-2] + tokens[-1]]
    if house is None and len(tokens) >= 2 and _HOUSE_TOKEN.match(tokens[-1]):
        before = [t for t in tokens[:-1] if not (_kind_of(t) or _ordinal_of(t) is not None or t.isdigit())]
        if before:
            house = tokens.pop()
    return AddressQuery(_split_street(tokens), normalize_house(house) if house else None)


def parse_voe_street(value: str) -> StreetName:
    """VOE autocomplete format: "провулок. 1-й Ботанічний"."""
    s = _clean(value)
    kind = None
    if ". " in s:
        raw_kind, s = s.split(". ", 1)
        kind = KIND_SYNONYMS.get(raw_kind, raw_kind)
    ordinal = None
    # "1-й Ботанічний" and "8 Березня": a leading number is the ordinal, as in user queries
    m = re.match(r"^(\d+)(?:-?(?:й|ий|ій|а|я|е))?\s+(\S.*)$", s)
    if m:
        ordinal, s = int(m.group(1)), m.group(2)
    return StreetName(kind, ordinal, s)


def parse_plain_street(text: str) -> StreetName:
    """Planned-works format: "вулиця Стрілецька", "* 1-й Маріі ...", "вулиця Хмельницьке шосе"."""
    street = _split_street(_clean(text).split())
    words = street.name.split()
    # "вулиця Хмельницьке шосе": the generic "вулиця" yields to the kind word inside the name
    if street.kind == "вулиця" and len(words) > 1 and _kind_of(words[-1]):
        return StreetName(_kind_of(words[-1]), street.ordinal, " ".join(words[:-1]))
    return street


def search_stem(street: StreetName) -> str:
    words = [w for w in re.split(r"[\s/]+", street.name) if w and not w.isdigit()]
    longest = max(words, key=len) if words else street.name
    stem = longest[:5]
    return stem[:1].upper() + stem[1:]


def _words(name: str) -> list[str]:
    return [w for w in re.split(r"[\s/]+", name) if w]


def street_matches(query: StreetName, cand: StreetName) -> bool:
    if query.kind is not None and query.kind != cand.kind:
        return False
    if query.ordinal is not None and query.ordinal != cand.ordinal:
        return False
    cand_words = _words(cand.name)
    for w in _words(query.name):
        prefix = w[: max(4, len(w) - 2)]
        if not any(c.startswith(prefix) for c in cand_words):
            return False
    return bool(_words(query.name))
