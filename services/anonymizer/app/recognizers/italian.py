"""Riconoscitori a regole per i dati personali italiani a formato fisso.

Dove esiste un carattere di controllo (CF, P.IVA, IBAN) lo verifichiamo:
così un numero a caso di 11 cifre non diventa una partita IVA.
"""
import re
from presidio_analyzer import Pattern, PatternRecognizer

LANG = "it"

# ── Codice fiscale ──────────────────────────────────────────────────────
# Le cifre possono essere sostituite da lettere (omocodia): LMNPQRSTUV.
_CF_DIGIT = "[0-9LMNPQRSTUV]"
_CF_REGEX = (
    rf"\b[A-Z]{{6}}{_CF_DIGIT}{{2}}[ABCDEHLMPRST]{_CF_DIGIT}{{2}}"
    rf"[A-Z]{_CF_DIGIT}{{3}}[A-Z]\b"
)

_CF_ODD = {
    **dict(zip("0123456789", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21])),
    **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [
        1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12,
        14, 16, 10, 22, 25, 24, 23,
    ])),
}


def _cf_even(c: str) -> int:
    return int(c) if c.isdigit() else ord(c) - ord("A")


def is_valid_cf(cf: str) -> bool:
    cf = cf.upper().replace(" ", "")
    if len(cf) != 16:
        return False
    total = 0
    for i, c in enumerate(cf[:15]):
        # Posizioni 1,3,5... (indice pari) sono "dispari" nella specifica.
        total += _CF_ODD[c] if i % 2 == 0 else _cf_even(c)
    return chr(ord("A") + total % 26) == cf[15]


# ── Partita IVA ─────────────────────────────────────────────────────────
def is_valid_piva(piva: str) -> bool:
    digits = [int(c) for c in piva if c.isdigit()]
    if len(digits) != 11 or not any(digits):
        return False
    total = 0
    for i, d in enumerate(digits[:10]):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10 == digits[10]


# ── IBAN ────────────────────────────────────────────────────────────────
def is_valid_iban(iban: str) -> bool:
    iban = iban.replace(" ", "").upper()
    if not 15 <= len(iban) <= 34:
        return False
    rearranged = iban[4:] + iban[:4]
    try:
        number = "".join(str(int(c, 36)) for c in rearranged)
    except ValueError:
        return False
    return int(number) % 97 == 1


class _ChecksumRecognizer(PatternRecognizer):
    """PatternRecognizer che scarta i match con checksum errato."""

    validator = staticmethod(lambda _: True)

    def validate_result(self, pattern_text: str) -> bool | None:
        # True → score alzato a 1.0; False → match scartato.
        return bool(self.validator(pattern_text))


class CodiceFiscaleRecognizer(_ChecksumRecognizer):
    validator = staticmethod(is_valid_cf)

    def __init__(self) -> None:
        super().__init__(
            supported_entity="CODICE_FISCALE",
            supported_language=LANG,
            patterns=[Pattern("cf", _CF_REGEX, 0.6)],
            context=["fiscale", "c.f.", "cf"],
            global_regex_flags=re.IGNORECASE,
        )


class PartitaIvaRecognizer(_ChecksumRecognizer):
    validator = staticmethod(is_valid_piva)

    def __init__(self) -> None:
        super().__init__(
            supported_entity="PARTITA_IVA",
            supported_language=LANG,
            # Il contesto si confronta parola per parola (lemmi spaCy):
            # niente frasi tipo "partita iva", servono le singole parole.
            # Lo 0.3 resta sotto soglia se manca il contesto: il checksum
            # da solo passa per 1 numero a caso su 10.
            patterns=[Pattern("piva", r"\b(?:IT\s?)?\d{11}\b", 0.3)],
            context=["iva", "p.iva", "piva", "p.i.", "partita", "vat"],
        )

    def validate_result(self, pattern_text: str) -> bool | None:
        # Checksum giusto non basta a portare a 1.0: decide il contesto.
        return None if is_valid_piva(pattern_text) else False


class IbanRecognizer(_ChecksumRecognizer):
    validator = staticmethod(is_valid_iban)

    def __init__(self) -> None:
        super().__init__(
            supported_entity="IBAN",
            supported_language=LANG,
            patterns=[Pattern(
                "iban",
                r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b",
                0.5,
            )],
            context=["iban", "conto", "bonifico"],
            global_regex_flags=re.IGNORECASE,
        )


def build_italian_recognizers() -> list[PatternRecognizer]:
    return [
        CodiceFiscaleRecognizer(),
        PartitaIvaRecognizer(),
        IbanRecognizer(),
        PatternRecognizer(
            supported_entity="EMAIL",
            supported_language=LANG,
            patterns=[Pattern(
                "email", r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Z]{2,}\b", 0.9,
            )],
        ),
        PatternRecognizer(
            supported_entity="TELEFONO",
            supported_language=LANG,
            patterns=[
                # Cellulari: 3xx xxx xxxx, con o senza +39.
                Pattern(
                    "cell",
                    r"(?<![\w+])(?:\+39[\s.-]?|0039[\s.-]?)?3\d{2}[\s.-]?\d{3}[\s.-]?\d{3,4}\b",
                    0.6,
                ),
                # Fissi: 0 + prefisso, 6–11 cifre in totale.
                Pattern(
                    "fisso",
                    r"(?<![\w+])(?:\+39[\s.-]?|0039[\s.-]?)?0\d{1,3}[\s./-]?\d{3,4}[\s.-]?\d{2,4}\b",
                    0.4,
                ),
            ],
            context=["tel", "telefono", "cell", "cellulare", "fax", "chiamare"],
        ),
        PatternRecognizer(
            supported_entity="TARGA",
            supported_language=LANG,
            patterns=[Pattern("targa", r"\b[A-HJ-NPR-TV-Z]{2}\s?\d{3}\s?[A-HJ-NPR-TV-Z]{2}\b", 0.3)],
            context=["targa", "targato", "veicolo", "auto", "moto"],
            global_regex_flags=re.IGNORECASE,
        ),
    ]
