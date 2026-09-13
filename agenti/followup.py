"""
Agente FOLLOW-UP: dopo una biopsia, attende l'esito istologico, lo confronta
con l'ipotesi del classificatore simulato (registro di audit), programma il
prossimo controllo periodico e tiene aggiornato il paziente.

PRINCIPIO FONDAMENTALE (vedi CLAUDE.md): come l'agente INSTRADAMENTO, questo
agente non usa il modello linguistico — non c'è nessun testo clinico da
adattare caso per caso, solo messaggi operativi fissi. Non prende MAI
decisioni cliniche: la classificazione istologica la sceglie il dermatologo
(tra un vocabolario fisso, vedi nucleo/registro_audit.py); questo agente si
limita a registrarla, confrontarla con l'ipotesi del classificatore, e
programmare la logistica conseguente.

Il testo mostrato al paziente quando l'esito arriva NON rivela MAI la
classificazione istologica: solo che l'esito è disponibile e che il
dermatologo la contatterà — stesso principio già rispettato per la
classificazione del classificatore simulato (agenti/analisi.py).

DATA SIMULATA (vedi nucleo/tempo_simulato.py): come INSTRADAMENTO, questo
agente usa la data simulata per datare solleciti e controlli programmati, non
la data reale.
"""

from datetime import timedelta

from nucleo import tempo_simulato
from nucleo.database import ottieni_connessione
from nucleo.registro_audit import categorizza_confronto
from nucleo.regole_sicurezza import decidi_intervallo_controllo
from nucleo.registro_azioni import registra_azione

NOME_AGENTE = "FOLLOW-UP"

# Giorni di cui avanza la data simulata a ogni sollecito per un esito
# istologico che non è ancora arrivato (vedi il pulsante nella pagina
# Dermatologo): un valore fisso nel codice, come per i solleciti della
# televisita (agenti/instradamento.py).
GIORNI_AVANZAMENTO_PER_SOLLECITO_ISTOLOGICO_DEMO = 7


def _gia_destinato_indipendentemente_dal_classificatore(connessione, caso_id: int) -> bool:
    """Ricostruisce, per un caso, se sarebbe comunque arrivato al dermatologo
    per una regola di sicurezza (neo dichiarato cambiato, o rischio
    costituzionale alto), indipendentemente da cosa avesse detto il
    classificatore — stessa condizione già usata in
    nucleo.regole_sicurezza.decidi_percorso, non salvata di nuovo altrove."""
    riga = connessione.execute(
        """SELECT c.priorita, q.neo_cambiato
           FROM casi c
           JOIN questionari q ON q.paziente_id = c.paziente_id
           WHERE c.id = ?
           ORDER BY q.id DESC LIMIT 1""",
        (caso_id,),
    ).fetchone()
    if riga is None:
        raise ValueError(f"Nessun questionario trovato per il caso {caso_id}.")
    priorita, neo_cambiato = riga
    return bool(neo_cambiato) or priorita == "alta"


def _ultima_classificazione_algoritmo(connessione, caso_id: int) -> str:
    """Legge l'ultimo esito del classificatore simulato per la lesione di
    questo caso (stesso collegamento foto→lesione→caso di agenti/analisi.py)."""
    riga = connessione.execute(
        """SELECT ac.esito
           FROM analisi_classificatore ac
           JOIN foto_lesioni fl ON fl.id = ac.foto_id
           JOIN casi c ON c.lesione_id = fl.lesione_id
           WHERE c.id = ?
           ORDER BY ac.id DESC LIMIT 1""",
        (caso_id,),
    ).fetchone()
    if riga is None:
        raise ValueError(f"Nessuna analisi del classificatore trovata per il caso {caso_id}.")
    return riga[0]


def carica_esito_istologico(caso_id: int, classificazione_istologica: str) -> dict:
    """Il dermatologo carica l'esito istologico di una biopsia (scelto tra le
    5 classificazioni predefinite, vedi nucleo/registro_audit.py): registra il
    confronto con l'ipotesi del classificatore simulato, chiude il caso e
    programma il prossimo controllo periodico."""
    connessione = ottieni_connessione()
    try:
        riga_caso = connessione.execute(
            "SELECT paziente_id, priorita FROM casi WHERE id = ?", (caso_id,)
        ).fetchone()
        if riga_caso is None:
            raise ValueError(f"Nessun caso trovato con id {caso_id}")
        paziente_id, priorita = riga_caso

        esito_gia_presente = connessione.execute(
            "SELECT 1 FROM esiti_istologici WHERE caso_id = ?", (caso_id,)
        ).fetchone()
        if esito_gia_presente is not None:
            raise ValueError(f"Il caso {caso_id} ha già un esito istologico caricato.")

        classificazione_algoritmo = _ultima_classificazione_algoritmo(connessione, caso_id)
        gia_destinato = _gia_destinato_indipendentemente_dal_classificatore(connessione, caso_id)
        categoria = categorizza_confronto(
            classificazione_algoritmo=classificazione_algoritmo,
            classificazione_istologica=classificazione_istologica,
            gia_destinato_indipendentemente_dal_classificatore=gia_destinato,
        )

        istante_simulato = tempo_simulato.ottieni_istante_simulato()
        connessione.execute(
            """INSERT INTO esiti_istologici (caso_id, classificazione, categoria_confronto, data_caricamento)
               VALUES (?, ?, ?, ?)""",
            (caso_id, classificazione_istologica, categoria, istante_simulato.isoformat(timespec="seconds")),
        )
        connessione.execute("UPDATE casi SET stato = 'chiuso_con_esito' WHERE id = ?", (caso_id,))

        intervallo = decidi_intervallo_controllo(priorita=priorita, classificazione_istologica=classificazione_istologica)
        data_controllo = (istante_simulato.date() + timedelta(days=intervallo["giorni"])).isoformat()
        connessione.execute(
            """INSERT INTO controlli_periodici (paziente_id, data_prevista, note, stato)
               VALUES (?, ?, ?, 'programmato')""",
            (paziente_id, data_controllo, intervallo["motivo"]),
        )
        connessione.commit()
    finally:
        connessione.close()

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=f"Caso {caso_id}: esito istologico caricato ({classificazione_istologica}).",
        decisione=f"Confronto registrato: {categoria.replace('_', ' ')}",
        motivo=(
            f"Ipotesi del classificatore: {classificazione_algoritmo.replace('_', ' ')}; "
            f"esito istologico: {classificazione_istologica.replace('_', ' ')}. "
            f"Prossimo controllo programmato: {intervallo['motivo']}"
        ),
        caso_id=caso_id,
        data_ora=istante_simulato.isoformat(timespec="seconds"),
    )

    return {
        "caso_id": caso_id,
        "classificazione_istologica": classificazione_istologica,
        "categoria_confronto": categoria,
        "data_controllo": data_controllo,
    }


def sollecita_esito_istologico(appuntamento_id: int) -> dict:
    """Se l'esito istologico di una biopsia non è ancora arrivato, simula il
    passare di GIORNI_AVANZAMENTO_PER_SOLLECITO_ISTOLOGICO_DEMO giorni e
    registra un sollecito. Non fa nulla (e non fa avanzare la data) se l'esito
    è già stato caricato."""
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT caso_id FROM appuntamenti WHERE id = ? AND tipo = 'biopsia'", (appuntamento_id,)
        ).fetchone()
        if riga is None:
            raise ValueError(f"Nessun appuntamento di biopsia trovato con id {appuntamento_id}")
        caso_id = riga[0]

        if connessione.execute("SELECT 1 FROM esiti_istologici WHERE caso_id = ?", (caso_id,)).fetchone() is not None:
            return {
                "caso_id": caso_id,
                "azione": "nessuna",
                "motivo": "L'esito istologico è già stato caricato.",
            }

        riga_notifica = connessione.execute(
            """SELECT id, numero_solleciti FROM notifiche
               WHERE caso_id = ? AND tipo = 'invito_biopsia' ORDER BY id DESC LIMIT 1""",
            (caso_id,),
        ).fetchone()
        if riga_notifica is None:
            raise ValueError(f"Nessuna notifica di biopsia trovata per il caso {caso_id}.")
        notifica_id, numero_solleciti_attuale = riga_notifica

        tempo_simulato.avanza_data_simulata(GIORNI_AVANZAMENTO_PER_SOLLECITO_ISTOLOGICO_DEMO)
        istante_simulato = tempo_simulato.ottieni_istante_simulato()

        nuovo_numero = (numero_solleciti_attuale or 0) + 1
        connessione.execute(
            "UPDATE notifiche SET numero_solleciti = ?, data_invio = ? WHERE id = ?",
            (nuovo_numero, istante_simulato.isoformat(timespec="seconds"), notifica_id),
        )
        connessione.commit()
    finally:
        connessione.close()

    motivo = (
        f"Sono passati {GIORNI_AVANZAMENTO_PER_SOLLECITO_ISTOLOGICO_DEMO} giorni simulati senza un esito "
        f"istologico: inviato il sollecito numero {nuovo_numero}."
    )
    registra_azione(
        agente=NOME_AGENTE,
        input_dati=f"Appuntamento di biopsia {appuntamento_id}, caso {caso_id}",
        decisione="Sollecito per esito istologico mancante",
        motivo=motivo,
        caso_id=caso_id,
        data_ora=istante_simulato.isoformat(timespec="seconds"),
    )

    return {"caso_id": caso_id, "azione": "sollecito_inviato", "numero_solleciti": nuovo_numero, "motivo": motivo}


def ottieni_casi_in_attesa_di_esito_istologico() -> list[dict]:
    """Casi con una biopsia richiesta e nessun esito istologico ancora
    caricato: per la pagina Dermatologo."""
    connessione = ottieni_connessione()
    try:
        righe = connessione.execute(
            """SELECT a.id, a.caso_id, p.nome, a.data_ora, n.numero_solleciti
               FROM appuntamenti a
               JOIN casi c ON c.id = a.caso_id
               JOIN pazienti p ON p.id = c.paziente_id
               LEFT JOIN notifiche n ON n.caso_id = a.caso_id AND n.tipo = 'invito_biopsia'
               WHERE a.tipo = 'biopsia'
                 AND NOT EXISTS (SELECT 1 FROM esiti_istologici e WHERE e.caso_id = a.caso_id)
               ORDER BY a.id ASC"""
        ).fetchall()
    finally:
        connessione.close()

    return [
        {
            "appuntamento_id": riga[0],
            "caso_id": riga[1],
            "nome_paziente": riga[2],
            "data_ora_biopsia": riga[3],
            "numero_solleciti": riga[4] or 0,
        }
        for riga in righe
    ]


def ottieni_stato_biopsia(caso_id: int) -> dict | None:
    """Stato della biopsia per un caso, per la pagina Paziente: SOLO se è in
    attesa o disponibile un esito, mai la classificazione istologica (vedi
    principio in cima al file). None se il caso non ha nessuna biopsia."""
    connessione = ottieni_connessione()
    try:
        riga_appuntamento = connessione.execute(
            "SELECT data_ora FROM appuntamenti WHERE caso_id = ? AND tipo = 'biopsia' ORDER BY id DESC LIMIT 1",
            (caso_id,),
        ).fetchone()
        if riga_appuntamento is None:
            return None
        esito_disponibile = (
            connessione.execute("SELECT 1 FROM esiti_istologici WHERE caso_id = ?", (caso_id,)).fetchone() is not None
        )
    finally:
        connessione.close()

    return {"data_ora_biopsia": riga_appuntamento[0], "esito_disponibile": esito_disponibile}


def ottieni_controlli_periodici(paziente_id: int) -> list[dict]:
    """Controlli periodici programmati per un paziente, dal più vicino."""
    connessione = ottieni_connessione()
    try:
        righe = connessione.execute(
            """SELECT data_prevista, note, stato FROM controlli_periodici
               WHERE paziente_id = ? ORDER BY data_prevista ASC""",
            (paziente_id,),
        ).fetchall()
    finally:
        connessione.close()

    return [{"data_prevista": riga[0], "motivo": riga[1], "stato": riga[2]} for riga in righe]
