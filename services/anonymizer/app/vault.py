"""Tabelle di corrispondenza pseudonimo ↔ valore originale, cifrate.

Una mappatura (mapping_id) raccoglie tutti i pseudonimi di un contesto:
un documento, una knowledge base, una conversazione. Dentro la stessa
mappatura lo stesso valore riceve sempre lo stesso pseudonimo.
I valori originali sono cifrati con Fernet; per ritrovarli senza
decifrare tutto usiamo un HMAC del valore normalizzato.
"""
import hashlib
import hmac
import sqlite3
import threading
import uuid
from pathlib import Path

from cryptography.fernet import Fernet


def normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


class Vault:
    def __init__(self, db_path: Path, key: str) -> None:
        self._fernet = Fernet(key.encode())
        self._hmac_key = hashlib.sha256(b"anonymizer-hmac" + key.encode()).digest()
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS mappings (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS entries (
                mapping_id TEXT NOT NULL REFERENCES mappings(id) ON DELETE CASCADE,
                token TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                value_hmac TEXT NOT NULL,
                value_enc BLOB NOT NULL,
                PRIMARY KEY (mapping_id, token),
                UNIQUE (mapping_id, entity_type, value_hmac)
            );
            """
        )
        # Additive migration: existing persistent mappings remain recoverable.
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(mappings)")}
        if "expires_at" not in columns:
            self._db.execute("ALTER TABLE mappings ADD COLUMN expires_at INTEGER")
        self._db.commit()
        self._db.execute("PRAGMA foreign_keys=ON")

    def _hmac(self, entity_type: str, value: str) -> str:
        msg = f"{entity_type}\x00{normalize(value)}".encode()
        return hmac.new(self._hmac_key, msg, hashlib.sha256).hexdigest()

    def ensure_mapping(self, mapping_id: str | None) -> str:
        mapping_id = mapping_id or str(uuid.uuid4())
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO mappings(id) VALUES (?)", (mapping_id,)
            )
        return mapping_id

    def token_for(self, mapping_id: str, entity_type: str, value: str) -> str:
        """Pseudonimo stabile per (mappatura, tipo, valore); lo crea se manca."""
        digest = self._hmac(entity_type, value)
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT token FROM entries WHERE mapping_id=? AND entity_type=? AND value_hmac=?",
                (mapping_id, entity_type, digest),
            ).fetchone()
            if row:
                return row[0]
            (count,) = self._db.execute(
                "SELECT COUNT(*) FROM entries WHERE mapping_id=? AND entity_type=?",
                (mapping_id, entity_type),
            ).fetchone()
            ephemeral = self._db.execute("SELECT expires_at FROM mappings WHERE id=?", (mapping_id,)).fetchone()
            token = (f"<PII_{uuid.UUID(mapping_id).hex}_{entity_type}_{count + 1}>"
                     if ephemeral and ephemeral[0] is not None else f"<{entity_type}_{count + 1}>")
            self._db.execute(
                "INSERT INTO entries VALUES (?, ?, ?, ?, ?)",
                (mapping_id, token, entity_type, digest,
                 self._fernet.encrypt(value.encode())),
            )
            return token

    def lookup(self, mapping_id: str) -> dict[str, str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT token, value_enc FROM entries WHERE mapping_id=?", (mapping_id,)
            ).fetchall()
        return {tok: self._fernet.decrypt(enc).decode() for tok, enc in rows}

    def exists(self, mapping_id: str) -> bool:
        with self._lock:
            return self._db.execute(
                "SELECT 1 FROM mappings WHERE id=? AND (expires_at IS NULL OR expires_at > unixepoch())", (mapping_id,)
            ).fetchone() is not None

    def create_temporary(self, mapping_id: str, ttl_seconds: int) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO mappings(id, expires_at) VALUES (?, unixepoch() + ?)",
                (mapping_id, ttl_seconds),
            )

    def expire(self) -> int:
        with self._lock, self._db:
            cur = self._db.execute("DELETE FROM mappings WHERE expires_at <= unixepoch()")
        return cur.rowcount

    def is_temporary(self, mapping_id: str) -> bool:
        with self._lock:
            row = self._db.execute("SELECT expires_at FROM mappings WHERE id=?", (mapping_id,)).fetchone()
        return bool(row and row[0] is not None)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def delete(self, mapping_id: str) -> bool:
        with self._lock, self._db:
            cur = self._db.execute("DELETE FROM mappings WHERE id=?", (mapping_id,))
        return cur.rowcount > 0
