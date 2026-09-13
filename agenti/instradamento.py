"""
Agente INSTRADAMENTO: per i casi già destinati al dermatologo, li mette in coda
per priorità, prenota una televisita su un'agenda simulata, invia la notifica
al paziente, gestisce i solleciti e l'eventuale scalo a un operatore umano.
Se il dermatologo decide una biopsia, prenota anche quella presso un centro
convenzionato simulato.

PRINCIPIO FONDAMENTALE (vedi CLAUDE.md): questo agente non decide MAI se un
caso va al dermatologo o se serve una biopsia — sono decisioni già prese
(dalle regole di sicurezza in nucleo.regole_sicurezza, o dal dermatologo in
carne e ossa). Si limita a organizzare agenda simulata e comunicazioni per un
caso già instradato. Non usa il modello linguistico: le notifiche sono
messaggi operativi fissi (data, ora, promemoria), non spiegazioni cliniche da
adattare caso per caso.

SOGLIA DI SOLLECITO (scritta nel codice, non affidata al modello linguistico):
dopo 2 solleciti senza conferma, l'appuntamento viene scalato a un operatore
umano, che contatta il paziente al di fuori della piattaforma.
"""

from datetime import date, datetime, timedelta

from nucleo.database import ottieni_connessione
from nucleo.registro_azioni import registra_azione

NOME_AGENTE = "INSTRADAMENTO"

_GIORNI_PRIMA_TELEVISITA = 3
_ORARIO_TELEVISITA_SIMULATO = "10:00"
_GIORNI_PRIMA_BIOPSIA = 7
_ORARIO_BIOPSIA_SIMULATO = "09:00"
_NUMERO_MASSIMO_SOLLECITI = 2
_CENTRO_CONVENZIONATO_SIMULATO = "Centro Dermatologico Convenzionato (demo)"

# A parità di data di apertura, i casi con priorità più alta vanno visti prima.
_ORDINE_PRIORITA = {"alta": 0, "media": 1, "bassa": 2}


def ottieni_coda_dermatologo() -> list[dict]:
    """Restituisce i casi in attesa di valutazione del dermatologo, ordinati per
    priorità (alta, poi media, poi bassa) e, a parità di priorità, dal caso
    aperto da più tempo al più recente."""
    connessione = ottieni_connessione()
    try:
        righe = connessione.execute(
            """SELECT c.id, p.nome, c.priorita, c.data_apertura, c.qualita_foto_insufficiente
               FROM casi c JOIN pazienti p ON p.id = c.paziente_id
               WHERE c.stato = 'in_coda_dermatologo'
               ORDER BY c.data_apertura ASC, c.id ASC"""
        ).fetchall()
    finally:
        connessione.close()

    casi = [
        {
            "caso_id": riga[0],
            "nome_paziente": riga[1],
            "priorita": riga[2],
            "data_apertura": riga[3],
            "qualita_foto_insufficiente": bool(riga[4]),
        }
        for riga in righe
    ]
    # Sort stabile: l'ordine per data_apertura dato dalla query SQL si conserva
    # a parità di priorità.
    casi.sort(key=lambda caso: _ORDINE_PRIORITA[caso["priorita"]])
    return casi


def ottieni_stato_instradamento(caso_id: int) -> dict | None:
    """Legge lo stato attuale (aggiornato) dell'appuntamento di televisita e
    della notifica collegata per un caso. None se il caso non è ancora stato
    instradato (nessuna televisita prenotata)."""
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            """SELECT a.id, a.data_ora, a.stato, n.numero_solleciti, n.confermata
               FROM appuntamenti a
               LEFT JOIN notifiche n ON n.caso_id = a.caso_id AND n.tipo = 'invito_televisita'
               WHERE a.caso_id = ? AND a.tipo = 'televisita'
               ORDER BY a.id DESC LIMIT 1""",
            (caso_id,),
        ).fetchone()
    finally:
        connessione.close()

    if riga is None:
        return None

    appuntamento_id, data_ora, stato_appuntamento, numero_solleciti, confermata = riga
    return {
        "appuntamento_id": appuntamento_id,
        "data_ora": data_ora,
        "stato_appuntamento": stato_appuntamento,
        "numero_solleciti": numero_solleciti or 0,
        "confermata": bool(confermata),
    }


def instrada_caso(caso_id: int) -> dict:
    """Punto di ingresso dell'agente INSTRADAMENTO per un caso già destinato al
    dermatologo (stato 'in_coda_dermatologo'). Prenota una televisita su
    un'agenda simulata e invia la notifica al paziente. Se il caso era già
    stato instradato (es. un rerun dell'interfaccia), non duplica
    l'appuntamento: restituisce quello già esistente."""
    connessione = ottieni_connessione()
    try:
        riga_caso = connessione.execute("SELECT stato FROM casi WHERE id = ?", (caso_id,)).fetchone()
        if riga_caso is None:
            raise ValueError(f"Nessun caso trovato con id {caso_id}")
        stato = riga_caso[0]
        if stato != "in_coda_dermatologo":
            raise ValueError(
                f"Il caso {caso_id} non è (ancora) destinato al dermatologo (stato attuale: {stato!r})."
            )

        appuntamento_esistente = connessione.execute(
            """SELECT id, data_ora, stato FROM appuntamenti
               WHERE caso_id = ? AND tipo = 'televisita' ORDER BY id DESC LIMIT 1""",
            (caso_id,),
        ).fetchone()
        if appuntamento_esistente is not None:
            appuntamento_id, data_ora, stato_appuntamento = appuntamento_esistente
            return {
                "caso_id": caso_id,
                "appuntamento_id": appuntamento_id,
                "data_ora": data_ora,
                "stato_appuntamento": stato_appuntamento,
                "gia_instradato": True,
            }

        data_ora_proposta = f"{(date.today() + timedelta(days=_GIORNI_PRIMA_TELEVISITA)).isoformat()} {_ORARIO_TELEVISITA_SIMULATO}"
        cursore = connessione.execute(
            """INSERT INTO appuntamenti (caso_id, tipo, data_ora, centro, stato)
               VALUES (?, 'televisita', ?, NULL, 'proposto')""",
            (caso_id, data_ora_proposta),
        )
        appuntamento_id = cursore.lastrowid

        testo_notifica = (
            f"Le proponiamo una televisita con il dermatologo per il {data_ora_proposta}. "
            "Confermi la disponibilità dall'app."
        )
        cursore_notifica = connessione.execute(
            """INSERT INTO notifiche (caso_id, tipo, testo, data_invio, confermata, numero_solleciti)
               VALUES (?, 'invito_televisita', ?, ?, 0, 0)""",
            (caso_id, testo_notifica, datetime.now().isoformat(timespec="seconds")),
        )
        notifica_id = cursore_notifica.lastrowid
        connessione.commit()
    finally:
        connessione.close()

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=f"Caso {caso_id} destinato al dermatologo.",
        decisione=f"Televisita proposta per il {data_ora_proposta}",
        motivo=(
            "Il caso è in coda per il dermatologo: prenotata una televisita su "
            "agenda simulata e inviata la notifica al paziente."
        ),
        caso_id=caso_id,
    )

    return {
        "caso_id": caso_id,
        "appuntamento_id": appuntamento_id,
        "notifica_id": notifica_id,
        "data_ora": data_ora_proposta,
        "stato_appuntamento": "proposto",
        "gia_instradato": False,
    }


def conferma_appuntamento(appuntamento_id: int) -> dict:
    """Il paziente conferma la disponibilità proposta: aggiorna l'appuntamento
    e la notifica collegata. Non è più necessario sollecitare chi ha già
    confermato."""
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT caso_id, stato FROM appuntamenti WHERE id = ?", (appuntamento_id,)
        ).fetchone()
        if riga is None:
            raise ValueError(f"Nessun appuntamento trovato con id {appuntamento_id}")
        caso_id, stato_attuale = riga
        if stato_attuale == "scalato_operatore":
            raise ValueError(
                f"L'appuntamento {appuntamento_id} è già stato scalato a un operatore umano: "
                "la conferma va gestita dall'operatore, non più dall'app."
            )

        connessione.execute("UPDATE appuntamenti SET stato = 'confermato' WHERE id = ?", (appuntamento_id,))
        connessione.execute(
            "UPDATE notifiche SET confermata = 1 WHERE caso_id = ? AND tipo = 'invito_televisita'",
            (caso_id,),
        )
        connessione.commit()
    finally:
        connessione.close()

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=f"Appuntamento {appuntamento_id}",
        decisione="Televisita confermata dal paziente",
        motivo="Il paziente ha confermato la disponibilità proposta.",
        caso_id=caso_id,
    )

    return {"caso_id": caso_id, "appuntamento_id": appuntamento_id, "stato_appuntamento": "confermato"}


def sollecita_appuntamento(appuntamento_id: int) -> dict:
    """Simula il passare del tempo senza conferma da parte del paziente: invia
    un sollecito, oppure — se erano già stati inviati 2 solleciti senza
    risposta — scala l'appuntamento a un operatore umano. Non fa nulla se
    l'appuntamento è già confermato o già scalato."""
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT caso_id, stato FROM appuntamenti WHERE id = ?", (appuntamento_id,)
        ).fetchone()
        if riga is None:
            raise ValueError(f"Nessun appuntamento trovato con id {appuntamento_id}")
        caso_id, stato_appuntamento = riga

        if stato_appuntamento == "confermato":
            return {
                "caso_id": caso_id,
                "appuntamento_id": appuntamento_id,
                "azione": "nessuna",
                "motivo": "L'appuntamento è già stato confermato dal paziente.",
            }
        if stato_appuntamento == "scalato_operatore":
            return {
                "caso_id": caso_id,
                "appuntamento_id": appuntamento_id,
                "azione": "nessuna",
                "motivo": "L'appuntamento era già stato scalato a un operatore umano.",
            }

        riga_notifica = connessione.execute(
            """SELECT id, numero_solleciti FROM notifiche
               WHERE caso_id = ? AND tipo = 'invito_televisita' ORDER BY id DESC LIMIT 1""",
            (caso_id,),
        ).fetchone()
        if riga_notifica is None:
            raise ValueError(f"Nessuna notifica di invito trovata per il caso {caso_id}.")
        notifica_id, numero_solleciti_attuale = riga_notifica

        if numero_solleciti_attuale >= _NUMERO_MASSIMO_SOLLECITI:
            connessione.execute("UPDATE appuntamenti SET stato = 'scalato_operatore' WHERE id = ?", (appuntamento_id,))
            connessione.commit()
            azione = "scalato_operatore"
            motivo = (
                f"Il paziente non ha confermato dopo {_NUMERO_MASSIMO_SOLLECITI} solleciti: "
                "il caso è stato scalato a un operatore umano."
            )
        else:
            nuovo_numero = numero_solleciti_attuale + 1
            connessione.execute(
                "UPDATE notifiche SET numero_solleciti = ?, data_invio = ? WHERE id = ?",
                (nuovo_numero, datetime.now().isoformat(timespec="seconds"), notifica_id),
            )
            connessione.commit()
            azione = "sollecito_inviato"
            motivo = f"Inviato il sollecito numero {nuovo_numero} di {_NUMERO_MASSIMO_SOLLECITI}: il paziente non ha ancora confermato."
    finally:
        connessione.close()

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=f"Appuntamento {appuntamento_id}, caso {caso_id}",
        decisione="Sollecito inviato" if azione == "sollecito_inviato" else "Caso scalato a operatore umano",
        motivo=motivo,
        caso_id=caso_id,
    )

    return {"caso_id": caso_id, "appuntamento_id": appuntamento_id, "azione": azione, "motivo": motivo}


def prenota_biopsia(caso_id: int) -> dict:
    """Prenota una biopsia presso il centro convenzionato simulato. Da chiamare
    SOLO dopo che il dermatologo ha deciso che serve una biopsia: questa
    decisione clinica non è mai presa da questo agente (vedi CLAUDE.md, sezioni
    3 e 6)."""
    connessione = ottieni_connessione()
    try:
        riga_caso = connessione.execute("SELECT id FROM casi WHERE id = ?", (caso_id,)).fetchone()
        if riga_caso is None:
            raise ValueError(f"Nessun caso trovato con id {caso_id}")

        data_ora_proposta = f"{(date.today() + timedelta(days=_GIORNI_PRIMA_BIOPSIA)).isoformat()} {_ORARIO_BIOPSIA_SIMULATO}"
        cursore = connessione.execute(
            """INSERT INTO appuntamenti (caso_id, tipo, data_ora, centro, stato)
               VALUES (?, 'biopsia', ?, ?, 'proposto')""",
            (caso_id, data_ora_proposta, _CENTRO_CONVENZIONATO_SIMULATO),
        )
        appuntamento_id = cursore.lastrowid

        testo_notifica = (
            f"È stata prenotata una biopsia presso {_CENTRO_CONVENZIONATO_SIMULATO} per il "
            f"{data_ora_proposta}, su indicazione del dermatologo."
        )
        connessione.execute(
            """INSERT INTO notifiche (caso_id, tipo, testo, data_invio, confermata, numero_solleciti)
               VALUES (?, 'invito_biopsia', ?, ?, 0, 0)""",
            (caso_id, testo_notifica, datetime.now().isoformat(timespec="seconds")),
        )
        connessione.commit()
    finally:
        connessione.close()

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=f"Caso {caso_id}: il dermatologo ha indicato una biopsia.",
        decisione=f"Biopsia prenotata per il {data_ora_proposta} presso il centro convenzionato",
        motivo=(
            "Prenotazione su agenda simulata del centro convenzionato, a seguito della "
            "decisione clinica del dermatologo (non presa da questo agente)."
        ),
        caso_id=caso_id,
    )

    return {
        "caso_id": caso_id,
        "appuntamento_id": appuntamento_id,
        "data_ora": data_ora_proposta,
        "centro": _CENTRO_CONVENZIONATO_SIMULATO,
    }
