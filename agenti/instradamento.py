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
umano, che contatta il paziente al di fuori della piattaforma. Scalo anche
indipendente dal conteggio: se la data simulata raggiunge quella
dell'appuntamento proposto senza conferma, si scala subito a un operatore,
anche se non erano ancora stati inviati 2 solleciti — non avrebbe senso
sollecitare per un appuntamento già scaduto.

DATA SIMULATA (vedi nucleo/tempo_simulato.py): questo agente non usa
date.today()/datetime.now() per datare notifiche, proposte di appuntamento,
solleciti ed escalation, ma la data simulata condivisa del progetto. Motivo:
senza una data che avanza, i due solleciti e l'escalation di un caso
risulterebbero inviati tutti nello stesso istante reale, e la sequenza
mostrata al pubblico contraddirebbe il racconto ("sono passati giorni senza
risposta"). Gli Agenti 1, 2 e 3 non sono toccati da questo: continuano a usare
la data reale.
"""

from datetime import date, timedelta

from nucleo import tempo_simulato
from nucleo.database import ottieni_connessione
from nucleo.registro_azioni import registra_azione

NOME_AGENTE = "INSTRADAMENTO"

_NUMERO_MASSIMO_SOLLECITI = 2

# Giorni di cui avanza la data simulata a ogni sollecito (vedi il pulsante
# demo nella pagina Paziente): un valore fisso nel codice, non lasciato al
# caso, perché deve rendere visibile lo scorrere del tempo fra un sollecito
# e l'altro nella cronologia del caso.
GIORNI_AVANZAMENTO_PER_SOLLECITO_DEMO = 2

# La televisita proposta deve cadere DOPO che i 2 solleciti e l'eventuale
# scalo a un operatore sarebbero comunque scattati (_NUMERO_MASSIMO_SOLLECITI
# + 1 avanzamenti: il "+1" è il momento dello scalo stesso), con un giorno di
# margine in più. Altrimenti la cronologia mostrerebbe un sollecito — o uno
# scalo a operatore — per un appuntamento già passato, il che contraddirebbe
# il racconto della demo (vedi anche il controllo di scadenza indipendente in
# sollecita_appuntamento, che copre comunque il caso anche se questi valori
# cambiassero in futuro).
_GIORNI_PRIMA_TELEVISITA = (_NUMERO_MASSIMO_SOLLECITI + 1) * GIORNI_AVANZAMENTO_PER_SOLLECITO_DEMO + 1
_ORARIO_TELEVISITA_SIMULATO = "10:00"
_GIORNI_PRIMA_BIOPSIA = 7
_ORARIO_BIOPSIA_SIMULATO = "09:00"
_CENTRO_CONVENZIONATO_SIMULATO = "Centro Dermatologico Convenzionato (demo)"

# A parità di data di apertura, i casi con priorità più alta vanno visti prima.
_ORDINE_PRIORITA = {"alta": 0, "media": 1, "bassa": 2}


def ottieni_coda_dermatologo() -> list[dict]:
    """Restituisce i casi in attesa di valutazione CLINICA del dermatologo,
    ordinati per priorità (alta, poi media, poi bassa) e, a parità di
    priorità, dal caso aperto da più tempo al più recente. Esclude i casi il
    cui appuntamento è stato scalato a un operatore umano (vedi
    ottieni_casi_scalati_a_operatore): quei casi non aspettano più una
    valutazione clinica, aspettano una telefonata — devono comparire solo
    nell'elenco separato, non anche qui, altrimenti il dermatologo non
    capirebbe a colpo d'occhio che per quel caso non c'è nulla da valutare."""
    connessione = ottieni_connessione()
    try:
        righe = connessione.execute(
            """SELECT c.id, p.nome, c.priorita, c.data_apertura, c.qualita_foto_insufficiente
               FROM casi c JOIN pazienti p ON p.id = c.paziente_id
               WHERE c.stato = 'in_coda_dermatologo'
                 AND NOT EXISTS (
                     SELECT 1 FROM appuntamenti a
                     WHERE a.caso_id = c.id AND a.tipo = 'televisita' AND a.stato = 'scalato_operatore'
                 )
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


def ottieni_casi_scalati_a_operatore() -> list[dict]:
    """Restituisce i casi il cui appuntamento di televisita è stato scalato a
    un operatore umano (dopo 2 solleciti senza risposta, o perché la data
    dell'appuntamento proposto è scaduta). Non richiedono una valutazione
    clinica del dermatologo, ma una telefonata dell'operatore: il messaggio
    già inviato al paziente lo promette esplicitamente, quindi deve comparire
    da qualche parte nell'interfaccia di chi lavora — qui, separato dalla
    coda ordinaria."""
    connessione = ottieni_connessione()
    try:
        righe = connessione.execute(
            """SELECT a.caso_id, p.nome, n.numero_solleciti
               FROM appuntamenti a
               JOIN casi c ON c.id = a.caso_id
               JOIN pazienti p ON p.id = c.paziente_id
               LEFT JOIN notifiche n ON n.caso_id = a.caso_id AND n.tipo = 'invito_televisita'
               WHERE a.tipo = 'televisita' AND a.stato = 'scalato_operatore'
               ORDER BY a.id DESC"""
        ).fetchall()

        casi = []
        for caso_id, nome_paziente, numero_solleciti in righe:
            riga_log = connessione.execute(
                """SELECT motivo, data_ora FROM log_agenti
                   WHERE caso_id = ? AND agente = ? AND decisione = 'Caso scalato a operatore umano'
                   ORDER BY id DESC LIMIT 1""",
                (caso_id, NOME_AGENTE),
            ).fetchone()
            motivo_escalation, data_ultima_azione = riga_log if riga_log is not None else (None, None)

            casi.append(
                {
                    "caso_id": caso_id,
                    "nome_paziente": nome_paziente,
                    "numero_solleciti": numero_solleciti or 0,
                    "motivo_escalation": motivo_escalation,
                    "data_ultima_azione": data_ultima_azione,
                }
            )
    finally:
        connessione.close()

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

        istante_simulato = tempo_simulato.ottieni_istante_simulato()
        data_ora_proposta = f"{(istante_simulato.date() + timedelta(days=_GIORNI_PRIMA_TELEVISITA)).isoformat()} {_ORARIO_TELEVISITA_SIMULATO}"
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
            (caso_id, testo_notifica, istante_simulato.isoformat(timespec="seconds")),
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
        data_ora=istante_simulato.isoformat(timespec="seconds"),
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
        data_ora=tempo_simulato.ottieni_istante_simulato().isoformat(timespec="seconds"),
    )

    return {"caso_id": caso_id, "appuntamento_id": appuntamento_id, "stato_appuntamento": "confermato"}


def sollecita_appuntamento(appuntamento_id: int) -> dict:
    """Simula il passare di GIORNI_AVANZAMENTO_PER_SOLLECITO_DEMO giorni senza
    conferma da parte del paziente: fa avanzare la data simulata di quei
    giorni e, di conseguenza, invia un sollecito oppure scala l'appuntamento a
    un operatore umano — sia perché erano già stati inviati 2 solleciti senza
    risposta, sia perché la data simulata ha raggiunto quella
    dell'appuntamento proposto (scaduto: non avrebbe senso sollecitare ancora).
    Non fa nulla (e non fa avanzare la data) se l'appuntamento è già
    confermato o già scalato: in quel caso non c'è nessuna attesa da
    simulare."""
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT caso_id, stato, data_ora FROM appuntamenti WHERE id = ?", (appuntamento_id,)
        ).fetchone()
        if riga is None:
            raise ValueError(f"Nessun appuntamento trovato con id {appuntamento_id}")
        caso_id, stato_appuntamento, data_ora_appuntamento = riga

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

        tempo_simulato.avanza_data_simulata(GIORNI_AVANZAMENTO_PER_SOLLECITO_DEMO)
        istante_simulato = tempo_simulato.ottieni_istante_simulato()

        # data_ora_appuntamento è "AAAA-MM-GG HH:MM": basta la parte data per
        # confrontarla con la data simulata (vedi il controllo indipendente
        # descritto sopra e nella SOGLIA DI SOLLECITO in cima al file).
        data_appuntamento = date.fromisoformat(data_ora_appuntamento.split(" ")[0])
        appuntamento_scaduto = istante_simulato.date() >= data_appuntamento

        if appuntamento_scaduto or numero_solleciti_attuale >= _NUMERO_MASSIMO_SOLLECITI:
            connessione.execute("UPDATE appuntamenti SET stato = 'scalato_operatore' WHERE id = ?", (appuntamento_id,))
            connessione.commit()
            azione = "scalato_operatore"
            if appuntamento_scaduto:
                motivo = (
                    f"La data dell'appuntamento proposto ({data_ora_appuntamento}) è stata raggiunta senza "
                    "conferma: il caso è stato scalato a un operatore umano."
                )
            else:
                motivo = (
                    f"Sono passati {GIORNI_AVANZAMENTO_PER_SOLLECITO_DEMO} giorni simulati e il paziente "
                    f"non ha confermato dopo {_NUMERO_MASSIMO_SOLLECITI} solleciti: il caso è stato scalato "
                    "a un operatore umano."
                )
        else:
            nuovo_numero = numero_solleciti_attuale + 1
            connessione.execute(
                "UPDATE notifiche SET numero_solleciti = ?, data_invio = ? WHERE id = ?",
                (nuovo_numero, istante_simulato.isoformat(timespec="seconds"), notifica_id),
            )
            connessione.commit()
            azione = "sollecito_inviato"
            motivo = (
                f"Sono passati {GIORNI_AVANZAMENTO_PER_SOLLECITO_DEMO} giorni simulati senza risposta: "
                f"inviato il sollecito numero {nuovo_numero} di {_NUMERO_MASSIMO_SOLLECITI}."
            )
    finally:
        connessione.close()

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=f"Appuntamento {appuntamento_id}, caso {caso_id}",
        decisione="Sollecito inviato" if azione == "sollecito_inviato" else "Caso scalato a operatore umano",
        motivo=motivo,
        caso_id=caso_id,
        data_ora=istante_simulato.isoformat(timespec="seconds"),
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

        istante_simulato = tempo_simulato.ottieni_istante_simulato()
        data_ora_proposta = f"{(istante_simulato.date() + timedelta(days=_GIORNI_PRIMA_BIOPSIA)).isoformat()} {_ORARIO_BIOPSIA_SIMULATO}"
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
            (caso_id, testo_notifica, istante_simulato.isoformat(timespec="seconds")),
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
        data_ora=istante_simulato.isoformat(timespec="seconds"),
    )

    return {
        "caso_id": caso_id,
        "appuntamento_id": appuntamento_id,
        "data_ora": data_ora_proposta,
        "centro": _CENTRO_CONVENZIONATO_SIMULATO,
    }
