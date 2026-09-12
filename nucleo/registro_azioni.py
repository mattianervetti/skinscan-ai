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
) -> None:
    """Scrive una riga nel registro delle azioni, con data e ora correnti."""
    connessione = ottieni_connessione()
    try:
        connessione.execute(
            """INSERT INTO log_agenti (caso_id, agente, input, decisione, motivo, data_ora)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (caso_id, agente, input_dati, decisione, motivo, datetime.now().isoformat(timespec="seconds")),
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
