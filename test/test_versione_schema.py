"""
Test del meccanismo di versione dello schema (nucleo/database.py): verifica che
un database con schema vecchio (o senza versione registrata) venga ricreato
automaticamente e correttamente all'avvio, senza errori.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.database import PERCORSO_DATABASE, VERSIONE_SCHEMA, inizializza_database, ottieni_connessione


def _crea_database_vecchio_senza_colonna_confidenza() -> None:
    """Simula un database creato prima dell'introduzione della colonna
    'confidenza' (lo schema reale usato in produzione prima di questo fix), e
    NON imposta PRAGMA user_version: rappresenta esattamente il caso segnalato
    ("table analisi_classificatore has no column named confidenza")."""
    if PERCORSO_DATABASE.exists():
        PERCORSO_DATABASE.unlink()

    PERCORSO_DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connessione = sqlite3.connect(PERCORSO_DATABASE)
    try:
        connessione.executescript(
            """
            CREATE TABLE pazienti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                eta INTEGER NOT NULL,
                fototipo INTEGER NOT NULL,
                data_creazione TEXT NOT NULL
            );
            CREATE TABLE foto_lesioni (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesione_id INTEGER NOT NULL,
                percorso_file TEXT NOT NULL,
                data_scatto TEXT NOT NULL,
                qualita_ok INTEGER NOT NULL,
                note_qualita TEXT
            );
            CREATE TABLE analisi_classificatore (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                foto_id INTEGER NOT NULL,
                esito TEXT NOT NULL CHECK (esito IN ('rassicurante', 'sospetto')),
                dettaglio TEXT,
                data_analisi TEXT NOT NULL
            );
            INSERT INTO pazienti (nome, eta, fototipo, data_creazione) VALUES ('Vecchio', 99, 2, '2020-01-01');
            """
        )
        connessione.commit()
        # PRAGMA user_version resta al valore di default (0): database "senza versione registrata".
    finally:
        connessione.close()


def test_database_vecchio_viene_ricreato_senza_errori():
    _crea_database_vecchio_senza_colonna_confidenza()

    # Prima del fix, un qualunque uso della colonna 'confidenza' avrebbe sollevato
    # sqlite3.OperationalError: table analisi_classificatore has no column named confidenza.
    inizializza_database()

    connessione = ottieni_connessione()
    try:
        versione_registrata = connessione.execute("PRAGMA user_version").fetchone()[0]
        colonne = [riga[1] for riga in connessione.execute("PRAGMA table_info(analisi_classificatore)").fetchall()]
        pazienti = connessione.execute("SELECT COUNT(*) FROM pazienti WHERE nome = 'Marta'").fetchone()[0]
        vecchio_paziente_ancora_presente = connessione.execute(
            "SELECT COUNT(*) FROM pazienti WHERE nome = 'Vecchio'"
        ).fetchone()[0]
    finally:
        connessione.close()

    assert versione_registrata == VERSIONE_SCHEMA
    assert "confidenza" in colonne, "la colonna 'confidenza' deve esistere dopo la ricreazione"
    assert pazienti == 1, "i dati demo devono essere stati ripopolati"
    assert vecchio_paziente_ancora_presente == 0, "il database vecchio deve essere stato cancellato, non solo aggiornato"


def test_database_aggiornato_non_viene_ricreato_inutilmente():
    inizializza_database()  # database già alla versione corrente (dal test precedente)

    connessione = ottieni_connessione()
    try:
        connessione.execute(
            "INSERT INTO pazienti (nome, eta, fototipo, data_creazione) VALUES ('Prova', 50, 2, '2026-01-01')"
        )
        connessione.commit()
    finally:
        connessione.close()

    inizializza_database()  # non deve azzerare i dati, la versione coincide già

    connessione = ottieni_connessione()
    try:
        presente = connessione.execute("SELECT COUNT(*) FROM pazienti WHERE nome = 'Prova'").fetchone()[0]
    finally:
        connessione.close()

    assert presente == 1, "un database già alla versione corrente non deve essere ricreato"


if __name__ == "__main__":
    test_database_vecchio_viene_ricreato_senza_errori()
    print("OK - database vecchio (senza colonna confidenza, senza versione registrata) ricreato correttamente")

    test_database_aggiornato_non_viene_ricreato_inutilmente()
    print("OK - database già aggiornato non viene ricreato inutilmente")

    print("\nTEST SUPERATO")
