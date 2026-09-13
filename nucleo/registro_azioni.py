"""
Registro delle azioni degli agenti: un'unica funzione per scrivere nella tabella
log_agenti, usata da tutti e cinque gli agenti. I testi passati devono essere già
leggibili da una persona non tecnica: questo modulo resta generico (nessuna
logica clinica), il contenuto leggibile lo prepara chi chiama.
"""

from datetime import datetime

from nucleo.database import ottieni_connessione


def registra_azione(
    agente: str,
    input_dati: str,
    decisione: str,
    motivo: str,
    caso_id: int | None = None,
    data_ora: str | None = None,
) -> None:
    """Scrive una riga nel registro delle azioni. Usa data e ora correnti se
    data_ora non è specificato (comportamento di sempre per la maggior parte
    degli agenti). L'agente INSTRADAMENTO passa invece esplicitamente la sua
    data simulata (vedi nucleo/tempo_simulato.py), per una cronologia coerente
    durante la demo: gli altri agenti non se ne accorgono, il parametro è
    facoltativo."""
    momento = data_ora if data_ora is not None else datetime.now().isoformat(timespec="seconds")
    connessione = ottieni_connessione()
    try:
        connessione.execute(
            """INSERT INTO log_agenti (caso_id, agente, input, decisione, motivo, data_ora)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (caso_id, agente, input_dati, decisione, motivo, momento),
        )
        connessione.commit()
    finally:
        connessione.close()


def elenca_azioni(limite: int | None = None) -> list[dict]:
    """Restituisce le azioni registrate, dalla più recente. Se limite è indicato,
    restituisce al massimo quel numero di azioni."""
    connessione = ottieni_connessione()
    try:
        if limite is not None:
            righe = connessione.execute(
                """SELECT agente, input, decisione, motivo, data_ora, caso_id
                   FROM log_agenti ORDER BY data_ora DESC, id DESC LIMIT ?""",
                (limite,),
            ).fetchall()
        else:
            righe = connessione.execute(
                """SELECT agente, input, decisione, motivo, data_ora, caso_id
                   FROM log_agenti ORDER BY data_ora DESC, id DESC"""
            ).fetchall()
    finally:
        connessione.close()

    return [
        {
            "agente": riga[0],
            "input": riga[1],
            "decisione": riga[2],
            "motivo": riga[3],
            "data_ora": riga[4],
            "caso_id": riga[5],
        }
        for riga in righe
    ]
