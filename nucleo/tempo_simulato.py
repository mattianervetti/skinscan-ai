"""
Data simulata del progetto, usata SOLO dall'agente INSTRADAMENTO (Fase 2,
agente 4) per datare notifiche, proposte di appuntamento, solleciti e scalo a
un operatore. Gli Agenti 1 (ACCOGLIENZA), 2 (GUIDA ALLA FOTO) e 3 (ANALISI)
restano invariati e continuano a usare la data e l'ora reali
(date.today()/datetime.now()): questo modulo non li riguarda.

MOTIVO (vedi CLAUDE.md): senza una data che avanza, i due solleciti e lo
scalo a un operatore del caso di Paolo risulterebbero inviati tutti nello
stesso istante reale (quello in cui, durante la demo, si clicca il
pulsante), e la sequenza mostrata al pubblico ("sono passati giorni senza
risposta") contraddirebbe le date registrate. La data simulata, memorizzata
nel database (tabella stato_demo, una sola riga) e avanzabile a comando,
rende la cronologia del caso coerente e leggibile durante la demo dal vivo.

Inizializzata alla data reale quando i dati demo vengono popolati (vedi
nucleo/database.py::inizializza_database e resetta_database), e riportata
alla data reale ogni volta che la demo viene reimpostata.
"""

from datetime import date, datetime, timedelta

from nucleo.database import ottieni_connessione

_ID_RIGA = 1


def inizializza_data_simulata(connessione) -> None:
    """Scrive la data simulata iniziale (= data reale odierna) nel database,
    usando la connessione già aperta da chi chiama (nucleo/database.py, nello
    stesso momento in cui popola i dati demo). Non apre né chiude la propria
    connessione e non fa il commit: lo fa chi chiama, insieme al resto."""
    connessione.execute("DELETE FROM stato_demo WHERE id = ?", (_ID_RIGA,))
    connessione.execute(
        "INSERT INTO stato_demo (id, data_simulata) VALUES (?, ?)",
        (_ID_RIGA, date.today().isoformat()),
    )


def ottieni_data_simulata() -> date:
    """Restituisce la data simulata corrente (solo il giorno, senza l'ora)."""
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT data_simulata FROM stato_demo WHERE id = ?", (_ID_RIGA,)
        ).fetchone()
    finally:
        connessione.close()

    if riga is None:
        raise RuntimeError(
            "Data simulata non inizializzata: inizializza_database() non è stata chiamata?"
        )
    return date.fromisoformat(riga[0])


def ottieni_istante_simulato() -> datetime:
    """Restituisce un timestamp completo da usare per gli eventi puntuali
    dell'agente INSTRADAMENTO (data_invio di una notifica, data_ora di un log):
    combina la data simulata con l'ora reale attuale, per avere un ordine
    leggibile anche fra più eventi avvenuti nello stesso giorno simulato,
    senza dover inventare un orario."""
    return datetime.combine(ottieni_data_simulata(), datetime.now().time())


def avanza_data_simulata(giorni: int) -> date:
    """Fa avanzare la data simulata di 'giorni' giorni e restituisce la nuova
    data. Usata dal pulsante demo dei solleciti nella pagina Paziente:
    ogni clic rappresenta il passare di quei giorni senza risposta."""
    nuova_data = ottieni_data_simulata() + timedelta(days=giorni)

    connessione = ottieni_connessione()
    try:
        connessione.execute(
            "UPDATE stato_demo SET data_simulata = ? WHERE id = ?",
            (nuova_data.isoformat(), _ID_RIGA),
        )
        connessione.commit()
    finally:
        connessione.close()

    return nuova_data
