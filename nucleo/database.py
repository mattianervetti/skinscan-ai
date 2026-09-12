"""
Modulo generico per il database SQLite del progetto: connessione, schema delle
tabelle, inizializzazione e reset. Non contiene dati specifici della demo
(quelli sono in nucleo/dati_demo.py) per restare riutilizzabile.
"""

import sqlite3
from pathlib import Path

# Percorso del file del database, calcolato con pathlib e relativo alla cartella
# del progetto: funziona identico su Windows e su Linux (Streamlit Community Cloud).
_CARTELLA_PROGETTO = Path(__file__).resolve().parent.parent
PERCORSO_DATABASE = _CARTELLA_PROGETTO / "data" / "skinscan.db"


def ottieni_connessione() -> sqlite3.Connection:
    """Apre una connessione al database, creando la cartella data/ se non esiste."""
    PERCORSO_DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connessione = sqlite3.connect(PERCORSO_DATABASE)
    connessione.execute("PRAGMA foreign_keys = ON")
    return connessione


# Schema completo del database: una tabella per ogni cosa che il sistema deve registrare.
_SCHEMA_SQL = """
-- Pazienti: anagrafica fittizia usata nella demo.
CREATE TABLE IF NOT EXISTS pazienti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    eta INTEGER NOT NULL,
    fototipo INTEGER NOT NULL,
    data_creazione TEXT NOT NULL
);

-- Questionari: le risposte raccolte dall'agente ACCOGLIENZA per un paziente.
CREATE TABLE IF NOT EXISTS questionari (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paziente_id INTEGER NOT NULL REFERENCES pazienti(id),
    data_compilazione TEXT NOT NULL,
    fototipo INTEGER NOT NULL,
    categoria_nei TEXT NOT NULL CHECK (categoria_nei IN ('<20', '20-50', '>50')),
    familiarita_melanoma INTEGER NOT NULL CHECK (familiarita_melanoma IN (0,1)),
    melanoma_pregresso INTEGER NOT NULL CHECK (melanoma_pregresso IN (0,1)),
    immunosoppressione INTEGER NOT NULL CHECK (immunosoppressione IN (0,1)),
    neo_cambiato INTEGER NOT NULL CHECK (neo_cambiato IN (0,1))
);

-- Lesioni: un neo monitorato nel tempo per un paziente.
CREATE TABLE IF NOT EXISTS lesioni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paziente_id INTEGER NOT NULL REFERENCES pazienti(id),
    etichetta TEXT NOT NULL,
    data_creazione TEXT NOT NULL
);

-- Foto delle lesioni: ogni scatto, con data e valutazione di qualità (nitida/sfocata).
CREATE TABLE IF NOT EXISTS foto_lesioni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesione_id INTEGER NOT NULL REFERENCES lesioni(id),
    percorso_file TEXT NOT NULL,
    data_scatto TEXT NOT NULL,
    qualita_ok INTEGER NOT NULL CHECK (qualita_ok IN (0,1)),
    note_qualita TEXT
);

-- Esiti del classificatore simulato (analizza_lesione) per una singola foto.
CREATE TABLE IF NOT EXISTS analisi_classificatore (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    foto_id INTEGER NOT NULL REFERENCES foto_lesioni(id),
    esito TEXT NOT NULL CHECK (esito IN ('rassicurante', 'sospetto')),
    dettaglio TEXT,
    data_analisi TEXT NOT NULL
);

-- Casi: il fascicolo di un paziente, con priorità, stato di avanzamento e il testo
-- effettivamente comunicato al paziente. Queste tre colonne (testo_paziente,
-- fonte_testo, data_testo) servono per tracciabilità: in ambito sanitario deve
-- essere ricostruibile cosa è stato comunicato, non solo quale decisione è stata
-- presa. Permettono anche al paziente di rivedere l'esito senza rigenerarlo, e di
-- non consumare quota del modello linguistico durante le demo.
-- qualita_foto_insufficiente è un flag separato da "stato": indica che la foto è
-- stata accettata dopo 3 tentativi falliti (regola di non esclusione dell'agente
-- GUIDA ALLA FOTO) e deve comparire ben visibile al dermatologo, indipendentemente
-- dalla fase in cui si trova il caso.
CREATE TABLE IF NOT EXISTS casi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paziente_id INTEGER NOT NULL REFERENCES pazienti(id),
    lesione_id INTEGER REFERENCES lesioni(id),
    priorita TEXT CHECK (priorita IN ('alta', 'media', 'bassa')),
    stato TEXT NOT NULL DEFAULT 'aperto',
    data_apertura TEXT NOT NULL,
    testo_paziente TEXT,
    fonte_testo TEXT CHECK (fonte_testo IN ('modello', 'riserva')),
    data_testo TEXT,
    qualita_foto_insufficiente INTEGER NOT NULL DEFAULT 0 CHECK (qualita_foto_insufficiente IN (0,1))
);

-- Decisioni del dermatologo su un caso: approvazione o modifica.
CREATE TABLE IF NOT EXISTS decisioni_dermatologo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caso_id INTEGER NOT NULL REFERENCES casi(id),
    decisione TEXT NOT NULL CHECK (decisione IN ('approvato', 'modificato')),
    motivo TEXT,
    data TEXT NOT NULL
);

-- Log delle azioni degli agenti: chi ha fatto cosa, con quale input e perché.
CREATE TABLE IF NOT EXISTS log_agenti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caso_id INTEGER REFERENCES casi(id),
    agente TEXT NOT NULL,
    input TEXT,
    decisione TEXT,
    motivo TEXT,
    data_ora TEXT NOT NULL
);

-- Notifiche simulate e conteggio dei solleciti inviati per un caso.
CREATE TABLE IF NOT EXISTS notifiche (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caso_id INTEGER NOT NULL REFERENCES casi(id),
    tipo TEXT NOT NULL,
    testo TEXT NOT NULL,
    data_invio TEXT NOT NULL,
    confermata INTEGER NOT NULL DEFAULT 0 CHECK (confermata IN (0,1)),
    numero_solleciti INTEGER NOT NULL DEFAULT 0
);

-- Appuntamenti: televisite e prenotazioni di biopsia (distinti dal campo "tipo").
CREATE TABLE IF NOT EXISTS appuntamenti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caso_id INTEGER NOT NULL REFERENCES casi(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('televisita', 'biopsia')),
    data_ora TEXT NOT NULL,
    centro TEXT,
    stato TEXT NOT NULL DEFAULT 'proposto'
);

-- Esiti istologici caricati dal paziente dopo una biopsia.
CREATE TABLE IF NOT EXISTS esiti_istologici (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caso_id INTEGER NOT NULL REFERENCES casi(id),
    esito_testo TEXT NOT NULL,
    data_caricamento TEXT NOT NULL
);

-- Controlli periodici programmati per un paziente.
CREATE TABLE IF NOT EXISTS controlli_periodici (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paziente_id INTEGER NOT NULL REFERENCES pazienti(id),
    data_prevista TEXT NOT NULL,
    note TEXT,
    stato TEXT NOT NULL DEFAULT 'programmato'
);
"""

# Ordine di cancellazione per il reset: le tabelle "figlie" prima delle "madri",
# per rispettare i riferimenti (foreign key) tra tabelle.
_TABELLE_IN_ORDINE_DI_CANCELLAZIONE = [
    "esiti_istologici",
    "appuntamenti",
    "notifiche",
    "log_agenti",
    "decisioni_dermatologo",
    "casi",
    "analisi_classificatore",
    "foto_lesioni",
    "lesioni",
    "controlli_periodici",
    "questionari",
    "pazienti",
]


def crea_paziente_con_questionario(
    *,
    nome: str,
    eta: int,
    fototipo: int,
    categoria_nei: str,
    familiarita_melanoma: bool,
    melanoma_pregresso: bool,
    immunosoppressione: bool,
    neo_cambiato: bool,
) -> int:
    """Inserisce un nuovo paziente e il suo questionario (usato dalla pagina
    Paziente quando si compila un questionario nuovo, non uno dei 4 demo).
    Restituisce l'id del paziente creato."""
    from datetime import date

    oggi = date.today().isoformat()

    connessione = ottieni_connessione()
    try:
        cursore = connessione.execute(
            "INSERT INTO pazienti (nome, eta, fototipo, data_creazione) VALUES (?, ?, ?, ?)",
            (nome, eta, fototipo, oggi),
        )
        id_paziente = cursore.lastrowid

        connessione.execute(
            """INSERT INTO questionari
               (paziente_id, data_compilazione, fototipo, categoria_nei,
                familiarita_melanoma, melanoma_pregresso, immunosoppressione, neo_cambiato)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id_paziente,
                oggi,
                fototipo,
                categoria_nei,
                int(familiarita_melanoma),
                int(melanoma_pregresso),
                int(immunosoppressione),
                int(neo_cambiato),
            ),
        )
        connessione.commit()
    finally:
        connessione.close()

    return id_paziente


def crea_tabelle(connessione: sqlite3.Connection) -> None:
    """Crea tutte le tabelle se non esistono già. Sicuro da chiamare più volte."""
    connessione.executescript(_SCHEMA_SQL)
    connessione.commit()


def _database_ha_dati(connessione: sqlite3.Connection) -> bool:
    cursore = connessione.execute("SELECT COUNT(*) FROM pazienti")
    return cursore.fetchone()[0] > 0


def inizializza_database() -> None:
    """Crea le tabelle se mancano e popola i dati demo se il database è vuoto.

    Va chiamata all'avvio dell'applicazione. Su Streamlit Community Cloud il disco
    viene azzerato a ogni riavvio dell'app: questa funzione ricrea tutto da zero,
    così l'app online non risulta mai vuota. In locale, se il database esiste già
    con dei dati, non li duplica.
    """
    # Importato qui (non in cima al file) per mantenere questo modulo indipendente
    # dai dati specifici della demo, che potranno cambiare senza toccare database.py.
    from nucleo.dati_demo import popola_dati_demo

    connessione = ottieni_connessione()
    try:
        crea_tabelle(connessione)
        if not _database_ha_dati(connessione):
            popola_dati_demo(connessione)
    finally:
        connessione.close()


def resetta_database() -> None:
    """Cancella tutti i dati e ricarica da zero i pazienti demo nella situazione
    di partenza. Utile per rifare la demo dal vivo senza riavviare l'applicazione."""
    from nucleo.dati_demo import popola_dati_demo

    connessione = ottieni_connessione()
    try:
        crea_tabelle(connessione)

        for tabella in _TABELLE_IN_ORDINE_DI_CANCELLAZIONE:
            connessione.execute(f"DELETE FROM {tabella}")

        # Azzera i contatori AUTOINCREMENT, solo se la tabella esiste già
        # (viene creata da SQLite solo dopo il primo inserimento).
        tabella_contatori_esiste = connessione.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        ).fetchone()
        if tabella_contatori_esiste:
            connessione.execute("DELETE FROM sqlite_sequence")

        connessione.commit()
        popola_dati_demo(connessione)
    finally:
        connessione.close()
