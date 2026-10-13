"""Test senza GLiNER (solo regole): girano su CPU in pochi secondi."""
import pytest
from cryptography.fernet import Fernet

from app.engine import Anonymizer
from app.recognizers.italian import is_valid_cf, is_valid_iban, is_valid_piva
from app.vault import Vault

# Valori sintetici con checksum valido, non appartengono a nessuno.
CF = "RSSMRA80A01H501U"
PIVA = "12345678903"
IBAN = "IT60X0542811101000000123456"


def test_checksums():
    assert is_valid_cf(CF)
    assert not is_valid_cf("RSSMRA80A01H501A")
    assert is_valid_piva(PIVA)
    assert not is_valid_piva("12345678901")
    assert is_valid_iban(IBAN)
    assert not is_valid_iban("IT60X0542811101000000123457")


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    vault = Vault(tmp_path_factory.mktemp("d") / "v.db", Fernet.generate_key().decode())
    return Anonymizer(vault, gliner=None, spacy_model="it_core_news_sm")


def test_pseudonimi_e_ritorno(engine):
    text = (
        f"Codice fiscale {CF}, partita IVA {PIVA}. "
        f"Bonifico su IBAN {IBAN}. Scrivere a mario.rossi@example.com "
        f"o al cell. +39 333 123 4567. Di nuovo: {CF}."
    )
    out, mapping_id, found = engine.anonymize(text, "pseudo", None)
    types = [f.entity_type for f in found]
    assert types.count("CODICE_FISCALE") == 2
    for t in ("PARTITA_IVA", "IBAN", "EMAIL", "TELEFONO"):
        assert t in types
    assert CF not in out and "example.com" not in out
    # Lo stesso CF riceve lo stesso pseudonimo.
    assert out.count("<CODICE_FISCALE_1>") == 2

    back, n = engine.deanonymize(out, mapping_id)
    assert back == text and n == len(found)


def test_mappatura_condivisa(engine):
    _, mid, _ = engine.anonymize(f"CF {CF}", "pseudo", None)
    out, _, _ = engine.anonymize(f"altro testo, codice fiscale {CF}", "pseudo", mid)
    assert "<CODICE_FISCALE_1>" in out


def test_piva_senza_contesto_non_basta(engine):
    out, _, found = engine.anonymize("Il numero 12345678903 è un ordine.", "redact", None)
    assert not found and "12345678903" in out


def test_redact(engine):
    out, mid, _ = engine.anonymize(f"cf: {CF}", "redact", None)
    assert mid is None and out == "cf: <CODICE_FISCALE>"


def test_token_senza_parentesi(engine):
    _, mid, _ = engine.anonymize(f"CF {CF}", "pseudo", None)
    back, _ = engine.deanonymize("Il titolare è CODICE_FISCALE_1.", mid)
    assert back == "Il titolare è CODICE_FISCALE_1."
