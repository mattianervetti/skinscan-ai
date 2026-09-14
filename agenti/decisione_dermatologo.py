"""
Agente/logica della decisione del dermatologo su un caso in coda (Fase 3,
passo 3). Non usa il modello linguistico: qui non c'è nessun testo da adattare
caso per caso, solo la registrazione di una decisione clinica già presa da una
persona in carne e ossa (mai da questo file, mai dal grafo — vedi CLAUDE.md,
sezioni 3 e 6).

Questo modulo non conosce LangGraph: è pensato per essere richiamabile e
testabile da solo, come gli altri agenti. Il nodo del grafo dedicato
(agenti/grafo_decisione_dermatologo.py) è un guscio sottile che chiama
decidi_e_applica().

PRINCIPIO CONDIVISO con nucleo.regole_sicurezza.decidi_proposta_dermatologo:
il sistema può solo PROPORRE un'azione; sceglierla resta sempre e solo del
dermatologo. Questo file registra quella scelta e SE coincide con la proposta
(colonna decisioni_dermatologo.decisione, 'approvato'/'modificato'): è l'unica
prova che la supervisione umana incida davvero sulle decisioni, non sia una
formalità (vedi nucleo/registro_audit.py per il conteggio).
"""

import json

from nucleo import tempo_simulato
from nucleo.database import PERCORSO_DATABASE, ottieni_connessione
from nucleo.registro_azioni import registra_azione
from nucleo.regole_sicurezza import (
    AZIONI_DERMATOLOGO_POSSIBILI,
    calcola_punteggio_rischio_costituzionale,
    decidi_percorso,
    decidi_proposta_dermatologo,
)

NOME_AGENTE = "DECISIONE DERMATOLOGO"

_CARTELLA_PROGETTO = PERCORSO_DATABASE.parent.parent

# Testo mostrato sia sul pulsante di decisione sia nel riquadro "cosa propone
# il sistema" (pages/dermatologo.py): stessa fonte per entrambi, quindi non
# possono mai divergere. "approva_televisita" non contiene la parola "approva"
# (Fase 3, passo 3.4, richiesta esplicita di Mattia): un'etichetta così invita
# a confermare senza dichiarare l'azione, esattamente l'inerzia che il
# principio "nessun valore preselezionato su un campo che registra un dato
# clinico" (CLAUDE.md, sezione 3) vuole evitare. Il valore interno
# 'approva_televisita' resta invariato: solo l'etichetta cambia, il confronto
# fra proposta e scelta (decisioni_dermatologo.decisione) continua a
# confrontare il valore, mai il testo mostrato.
ETICHETTE_AZIONE = {
    "approva_televisita": "Procedi con la televisita",
    "richiedi_biopsia": "Richiedi una biopsia",
    "chiudi_caso": "Chiudi il caso senza ulteriori accertamenti",
    "richiedi_nuova_foto": "Richiedi una nuova foto",
    "convoca_ambulatorio": "Convoca il paziente in ambulatorio",
}

# Stato del caso dopo ogni azione. None per 'richiedi_biopsia': il caso resta
# 'in_coda_dermatologo", l'esclusione dalla coda ordinaria è già gestita
# dall'esistenza dell'appuntamento di biopsia (agenti/instradamento.py::
# ottieni_coda_dermatologo, invariato). Nessun'altra azione tocca
# agenti/instradamento.py.
_STATO_DOPO_AZIONE = {
    "approva_televisita": "approvato_televisita",
    "richiedi_biopsia": None,
    "chiudi_caso": "chiuso_senza_accertamenti",
    "richiedi_nuova_foto": "attesa_nuova_foto",
    "convoca_ambulatorio": "convocato_ambulatorio",
}

STATO_ATTESA_NUOVA_FOTO = "attesa_nuova_foto"


def _leggi_classificazione_algoritmo(connessione, lesione_id: int) -> str:
    riga = connessione.execute(
        """SELECT ac.esito FROM analisi_classificatore ac
           JOIN foto_lesioni fl ON fl.id = ac.foto_id
           WHERE fl.lesione_id = ? ORDER BY ac.id DESC LIMIT 1""",
        (lesione_id,),
    ).fetchone()
    if riga is None:
        raise ValueError(f"Nessuna analisi del classificatore trovata per la lesione {lesione_id}.")
    return riga[0]


def ottieni_scheda_caso(caso_id: int) -> dict:
    """Raccoglie tutto il necessario per la scheda del caso nella pagina
    Dermatologo: questionario e punteggio di rischio (ricalcolato dal
    questionario salvato, funzioni pure — stesso principio già usato da
    agenti.accoglienza.rigenera_testo_paziente, mai una nuova decisione),
    fotografia accettata e precedente, esito del classificatore CON l'avviso
    di simulazione nello stesso blocco (mai separato, vedi
    nucleo/classificatore.py), confronto storico, qualità dell'immagine, e la
    proposta del sistema per l'azione da intraprendere."""
    connessione = ottieni_connessione()
    try:
        riga_caso = connessione.execute(
            """SELECT paziente_id, priorita, stato, qualita_foto_insufficiente, lesione_id, data_apertura
               FROM casi WHERE id = ?""",
            (caso_id,),
        ).fetchone()
        if riga_caso is None:
            raise ValueError(f"Nessun caso trovato con id {caso_id}")
        paziente_id, priorita, stato, qualita_foto_insufficiente, lesione_id, data_apertura = riga_caso
        qualita_foto_insufficiente = bool(qualita_foto_insufficiente)
        if lesione_id is None:
            raise ValueError(f"Il caso {caso_id} non ha ancora nessuna foto associata.")

        nome_paziente, eta = connessione.execute(
            "SELECT nome, eta FROM pazienti WHERE id = ?", (paziente_id,)
        ).fetchone()

        riga_questionario = connessione.execute(
            """SELECT fototipo, categoria_nei, familiarita_melanoma, melanoma_pregresso,
                      immunosoppressione, neo_cambiato
               FROM questionari WHERE paziente_id = ? ORDER BY id DESC LIMIT 1""",
            (paziente_id,),
        ).fetchone()
        fototipo, categoria_nei, familiarita, melanoma_pregresso, immunosoppressione, neo_cambiato = riga_questionario
        neo_cambiato = bool(neo_cambiato)

        info_punteggio = calcola_punteggio_rischio_costituzionale(
            eta=eta,
            fototipo=fototipo,
            categoria_nei=categoria_nei,
            familiarita_melanoma=bool(familiarita),
            melanoma_pregresso=bool(melanoma_pregresso),
            immunosoppressione=bool(immunosoppressione),
        )
        info_percorso = decidi_percorso(info_punteggio["priorita"], neo_cambiato)

        # Tutte le foto accettate, non solo le due più recenti (passo 3.4, vedi
        # sotto il motivo). ORDER BY id DESC, non LIMIT: la ricerca della foto
        # precedente deve poter scorrere all'indietro finché non trova un
        # contenuto diverso.
        righe_foto = connessione.execute(
            """SELECT id, percorso_file, data_scatto FROM foto_lesioni
               WHERE lesione_id = ? AND qualita_ok = 1 ORDER BY id DESC""",
            (lesione_id,),
        ).fetchall()
        if not righe_foto:
            raise ValueError(f"Nessuna foto accettata trovata per il caso {caso_id}.")

        foto_corrente = {
            "percorso_file": righe_foto[0][1],
            "data_scatto": righe_foto[0][2],
            "dati": (_CARTELLA_PROGETTO / righe_foto[0][1]).read_bytes(),
        }
        # Foto precedente: la più recente fra le altre con un contenuto
        # DIVERSO da quella attuale — stesso principio già usato in
        # agenti/analisi.py::_trova_foto_precedente_diversa ("stesso file
        # ricaricato = si ignora, si cerca più indietro"). Senza questo
        # controllo, un percorso guidato con un solo scatto accettato nella
        # sessione (il caso normale: sfocata rifiutata, poi nitida accettata,
        # quando la lesione ha già in archivio la STESSA foto nitida da una
        # visita precedente) mostrerebbe due volte lo stesso identico file,
        # rendendo il confronto inutile.
        foto_precedente = None
        for _id, percorso, data_scatto in righe_foto[1:]:
            dati = (_CARTELLA_PROGETTO / percorso).read_bytes()
            if dati != foto_corrente["dati"]:
                foto_precedente = {"percorso_file": percorso, "data_scatto": data_scatto, "dati": dati}
                break

        classificazione_algoritmo = _leggi_classificazione_algoritmo(connessione, lesione_id)

        riga_analisi = connessione.execute(
            """SELECT esito, confidenza, caratteristiche, confronto_storico, avviso_simulazione
               FROM analisi_classificatore WHERE foto_id = (
                   SELECT id FROM foto_lesioni WHERE lesione_id = ? AND qualita_ok = 1 ORDER BY id DESC LIMIT 1
               ) ORDER BY id DESC LIMIT 1""",
            (lesione_id,),
        ).fetchone()
        esito, confidenza, caratteristiche_json, confronto_storico, avviso_simulazione = riga_analisi
        analisi = {
            "classificazione": esito,
            "confidenza": confidenza,
            "caratteristiche": json.loads(caratteristiche_json) if caratteristiche_json else {},
            "confronto_storico": confronto_storico,
            "avviso_simulazione": avviso_simulazione,
        }
    finally:
        connessione.close()

    proposta = decidi_proposta_dermatologo(
        classificazione_algoritmo=classificazione_algoritmo,
        qualita_foto_insufficiente=qualita_foto_insufficiente,
    )

    return {
        "caso_id": caso_id,
        "nome_paziente": nome_paziente,
        "eta": eta,
        "priorita": priorita,
        "punteggio_rischio": info_punteggio["punteggio"],
        "motivo_priorita": f"{info_punteggio['motivo']} {info_percorso['motivo']}",
        "neo_cambiato": neo_cambiato,
        "stato": stato,
        "qualita_foto_insufficiente": qualita_foto_insufficiente,
        "data_apertura": data_apertura,
        "foto_corrente": foto_corrente,
        "foto_precedente": foto_precedente,
        "analisi": analisi,
        "proposta_sistema": proposta["proposta"],
        "motivo_proposta": proposta["motivo"],
    }


def decidi_e_applica(caso_id: int, azione_scelta: str) -> dict:
    """Unica funzione che scrive per una decisione del dermatologo: calcola la
    proposta del sistema, registra se la scelta la conferma o la modifica,
    applica l'effetto specifico dell'azione (cambio di stato del caso, ed
    eventualmente la prenotazione della biopsia tramite l'agente
    INSTRADAMENTO già esistente — mai duplicata qui) e registra tutto nel log
    delle azioni."""
    if azione_scelta not in AZIONI_DERMATOLOGO_POSSIBILI:
        raise ValueError(f"azione_scelta non valida: {azione_scelta!r}")

    connessione = ottieni_connessione()
    try:
        riga_caso = connessione.execute(
            "SELECT lesione_id, qualita_foto_insufficiente FROM casi WHERE id = ?", (caso_id,)
        ).fetchone()
        if riga_caso is None:
            raise ValueError(f"Nessun caso trovato con id {caso_id}")
        lesione_id, qualita_foto_insufficiente = riga_caso
        qualita_foto_insufficiente = bool(qualita_foto_insufficiente)

        classificazione_algoritmo = _leggi_classificazione_algoritmo(connessione, lesione_id)
        proposta_sistema = decidi_proposta_dermatologo(
            classificazione_algoritmo=classificazione_algoritmo,
            qualita_foto_insufficiente=qualita_foto_insufficiente,
        )["proposta"]

        decisione = "approvato" if azione_scelta == proposta_sistema else "modificato"

        istante_simulato = tempo_simulato.ottieni_istante_simulato()
        connessione.execute(
            """INSERT INTO decisioni_dermatologo
               (caso_id, proposta_sistema, azione_scelta, decisione, motivo, data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                caso_id,
                proposta_sistema,
                azione_scelta,
                decisione,
                f"Proposta del sistema: {ETICHETTE_AZIONE[proposta_sistema]}. "
                f"Scelta del dermatologo: {ETICHETTE_AZIONE[azione_scelta]}.",
                istante_simulato.isoformat(timespec="seconds"),
            ),
        )

        nuovo_stato = _STATO_DOPO_AZIONE[azione_scelta]
        if nuovo_stato is not None:
            connessione.execute("UPDATE casi SET stato = ? WHERE id = ?", (nuovo_stato, caso_id))

        connessione.commit()
    finally:
        connessione.close()

    # La prenotazione della biopsia è responsabilità dell'agente INSTRADAMENTO
    # (idempotente, già testato): chiamata SOLO dopo aver chiuso questa
    # connessione, per non tenere due scritture aperte sullo stesso file SQLite.
    if azione_scelta == "richiedi_biopsia":
        from agenti.instradamento import prenota_biopsia

        prenota_biopsia(caso_id)

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=f"Caso {caso_id}: proposta del sistema — {ETICHETTE_AZIONE[proposta_sistema]}.",
        decisione=f"Il dermatologo ha scelto: {ETICHETTE_AZIONE[azione_scelta]} ({decisione})",
        motivo=(
            "Decisione clinica del dermatologo, non del sistema (vedi CLAUDE.md, sezioni 3 e 6). "
            f"Confronto con la proposta del sistema: {decisione}."
        ),
        caso_id=caso_id,
        data_ora=istante_simulato.isoformat(timespec="seconds"),
    )

    return {
        "caso_id": caso_id,
        "proposta_sistema": proposta_sistema,
        "azione_scelta": azione_scelta,
        "decisione": decisione,
        "nuovo_stato": nuovo_stato,
    }


def ottieni_casi_in_attesa_nuova_foto() -> list[dict]:
    """Casi per cui il dermatologo ha richiesto una nuova foto: NON aspettano
    una valutazione clinica (non devono comparire nella coda ordinaria, da cui
    escono già da soli appena cambia casi.stato), aspettano un'azione del
    paziente. Per la pagina Dermatologo, in una sezione separata e ben
    etichettata: un caso così non deve sembrare "da valutare".

    LIMITE APERTO (annotato in CLAUDE.md, Fase 4): oggi non esiste ancora, dal
    lato paziente, un modo per ricaricare la foto di QUESTO caso specifico —
    la pagina Paziente crea sempre un caso nuovo. Finché quel collegamento non
    esiste, un caso qui resta bloccato: per questo deve restare visibile,
    invece di sparire come se fosse stato gestito."""
    connessione = ottieni_connessione()
    try:
        righe = connessione.execute(
            """SELECT c.id, p.nome,
                      (SELECT dd.data FROM decisioni_dermatologo dd
                       WHERE dd.caso_id = c.id ORDER BY dd.id DESC LIMIT 1)
               FROM casi c JOIN pazienti p ON p.id = c.paziente_id
               WHERE c.stato = ?
               ORDER BY c.id ASC""",
            (STATO_ATTESA_NUOVA_FOTO,),
        ).fetchall()
    finally:
        connessione.close()

    return [{"caso_id": riga[0], "nome_paziente": riga[1], "data_richiesta": riga[2]} for riga in righe]
