"""
Agente ACCOGLIENZA: valuta il questionario di un paziente e decide priorità e
percorso.

PRINCIPIO FONDAMENTALE (vedi CLAUDE.md): il modello linguistico NON decide mai
la priorità né il percorso del paziente. Queste decisioni sono calcolate SOLO
dalle funzioni pure di nucleo.regole_sicurezza, in modo deterministico e
testabile. Il modello linguistico viene usato SOLO per formulare in italiano
naturale la spiegazione destinata al paziente, DOPO che la decisione è già
stata presa e salvata nel database.

Questo file contiene funzioni Python normali, senza dipendenze dall'interfaccia
(Streamlit): in Fase 3 diventerà un nodo di un grafo LangGraph, ma per ora resta
una funzione richiamabile direttamente e testabile in isolamento.
"""

from datetime import date, datetime

from nucleo.database import ottieni_connessione
from nucleo.modello_linguistico import chiedi_al_modello
from nucleo.registro_azioni import registra_azione
from nucleo.regole_sicurezza import calcola_punteggio_rischio_costituzionale, decidi_percorso

NOME_AGENTE = "ACCOGLIENZA"

_ISTRUZIONE_DI_SISTEMA = (
    "Sei un assistente che comunica a un paziente, in un contesto sanitario, "
    "l'esito di una valutazione preliminare del rischio dermatologico. Segui "
    "OBBLIGATORIAMENTE queste regole:\n"
    "1. Registro linguistico formale (terza persona/\"lei\"), professionale ma "
    "comprensibile. Vietati: \"ciao\", punti esclamativi, linguaggio infantilizzante.\n"
    "2. Frasi brevi e verbi attivi (es. \"abbiamo esaminato i dati\", non \"i "
    "dati sono stati esaminati\"). Usa SOLO le azioni davvero descritte più "
    "sotto: non inventare passaggi (es. non nominare foto se non sono state "
    "richieste, non dire che il caso va allo specialista se non è così).\n"
    "3. Vietate le formule burocratiche, in qualunque forma, tra cui: \"il "
    "presente caso\", \"si invita pertanto\", \"la relativa valutazione\", \"le "
    "comunicazioni ufficiali\", \"la struttura sanitaria\", \"con successo\".\n"
    "4. Niente perifrasi: scrivi \"le fotografie che ha inviato\", non \"le "
    "immagini fotografiche da lei trasmesse\".\n"
    "5. Non rassicurare MAI sull'esito, in nessuna forma (vietate frasi come "
    "\"non si preoccupi\", \"stia sereno/a\", \"stia tranquillo/a\", \"sarà "
    "sicuramente nulla\", \"è probabilmente benigno\") e non allarmare MAI: tu "
    "non conosci l'esito clinico, comunicarlo come tranquillizzante o "
    "preoccupante sarebbe scorretto.\n"
    "6. Il genere del paziente non è noto: NON usare MAI aggettivi, participi o "
    "altre parole che richiedano un accordo di genere riferito al paziente "
    "(vietate forme come \"sereno/a\", \"sicuro/a\", \"gentile utente/utilizzatrice\", "
    "o qualunque scrittura con la barra \"/\"). Riformula sempre la frase in modo "
    "neutro, così da non doverne avere bisogno.\n"
    "7. Struttura fissa, in questo ordine: (a) cosa è emerso dalla valutazione, in "
    "termini di fattori considerati; (b) cosa succede adesso; (c) cosa deve fare "
    "concretamente il paziente come passo successivo.\n"
    "8. Ricorda sempre che la valutazione clinica finale spetta al dermatologo.\n"
    "9. Niente terminologia tecnica non spiegata.\n"
    "10. Massimo 5 frasi in tutto.\n"
    "11. Criterio generale: il testo deve suonare come un professionista "
    "sanitario che spiega con chiarezza a una persona, mai come una "
    "comunicazione amministrativa."
)

# Testi di riserva: usati SOLO se la chiamata al modello linguistico fallisce per
# qualsiasi motivo (chiave mancante, quota esaurita, rete assente). La decisione
# clinica (priorità e percorso) è calcolata comunque dal codice, indipendentemente
# da questo testo: qui cambia solo la formulazione mostrata al paziente. Seguono
# le stesse regole di tono dell'istruzione data al modello (vedi sopra): nessuna
# rassicurazione, nessun accordo di genere riferito al paziente.
_TESTO_RISERVA_PREVENZIONE = (
    "Dalla valutazione del questionario non sono emersi fattori di rischio "
    "significativi e non ha segnalato cambiamenti in corso in alcun neo. Al "
    "momento non sono necessari ulteriori esami. Le consigliamo di effettuare un "
    "autoesame della pelle circa ogni 2-3 mesi, osservando forma, colore e "
    "dimensione dei nei. Si rivolga a un medico anche prima del prossimo "
    "controllo se dovesse notare un neo che cambia rapidamente, sanguina o "
    "provoca prurito persistente. La valutazione clinica definitiva spetta in "
    "ogni caso a un dermatologo."
)
_TESTO_RISERVA_FOTO_SENZA_DERMATOLOGO = (
    "Dalla valutazione del questionario sono emersi alcuni fattori di rischio da "
    "approfondire, anche se non ha segnalato cambiamenti in un neo. Le chiediamo "
    "di inviare alcune fotografie guidate dei nei indicati. In base alle "
    "fotografie potremmo richiederle un ulteriore approfondimento. Prosegua con "
    "lo scatto guidato seguendo le istruzioni della piattaforma. La valutazione "
    "clinica finale spetta comunque a un dermatologo."
)
_TESTO_RISERVA_FOTO_CON_DERMATOLOGO = (
    "Dalla valutazione del questionario sono emersi elementi che richiedono un "
    "approfondimento clinico. Le chiediamo di inviare alcune fotografie guidate "
    "dei nei indicati. Un dermatologo esaminerà comunque il caso, a cui spetta "
    "ogni valutazione clinica. Prosegua con lo scatto guidato seguendo le "
    "istruzioni della piattaforma. Le invieremo poi le indicazioni per una "
    "televisita."
)


def _testo_di_riserva(percorso: str, destinato_dermatologo: bool) -> str:
    if percorso == "prevenzione":
        return _TESTO_RISERVA_PREVENZIONE
    if destinato_dermatologo:
        return _TESTO_RISERVA_FOTO_CON_DERMATOLOGO
    return _TESTO_RISERVA_FOTO_SENZA_DERMATOLOGO


def _stato_da_percorso(percorso: str, destinato_dermatologo: bool) -> str:
    if percorso == "prevenzione":
        return "monitoraggio_domiciliare"
    return "in_coda_dermatologo" if destinato_dermatologo else "attesa_foto"


def _percorso_da_stato(stato: str) -> tuple[str, bool]:
    if stato == "monitoraggio_domiciliare":
        return "prevenzione", False
    if stato == "attesa_foto":
        return "foto", False
    if stato == "in_coda_dermatologo":
        return "foto", True
    raise ValueError(f"stato del caso non riconosciuto: {stato!r}")


def _costruisci_domanda(motivo_fattori: str, percorso: str, destinato_dermatologo: bool, neo_cambiato: bool) -> str:
    return (
        f"Fattori considerati nella valutazione: {motivo_fattori} "
        f"Percorso assegnato: {percorso}. "
        f"{'Il caso sarà comunque esaminato da un dermatologo.' if destinato_dermatologo else ''} "
        f"{'Il paziente ha segnalato che un neo è cambiato di recente.' if neo_cambiato else 'Non sono stati segnalati sintomi in corso.'} "
        "Scrivi il messaggio per il paziente seguendo esattamente la struttura "
        "e le regole indicate nelle istruzioni di sistema."
        + (
            " Indica anche quando e con quale frequenza effettuare l'autoesame "
            "della pelle, e in quali casi rivolgersi a un medico anche prima del "
            "prossimo controllo programmato."
            if percorso == "prevenzione"
            else ""
        )
    )


def _genera_testo_e_fonte(domanda: str, percorso: str, destinato_dermatologo: bool) -> tuple[str, str, str | None]:
    """Prova a chiamare il modello linguistico (che internamente prova più
    modelli in catena, vedi nucleo.modello_linguistico.CATENA_MODELLI); qualsiasi
    errore (chiave mancante, quota esaurita su tutta la catena, rete assente,
    modello disattivato da configurazione) viene intercettato e sostituito da un
    testo di riserva, senza mai propagare l'eccezione a chi chiama.

    Restituisce (testo, fonte_testo, nome_modello_usato). nome_modello_usato è
    None quando si è usato il testo di riserva."""
    try:
        testo, nome_modello = chiedi_al_modello(domanda, istruzione_di_sistema=_ISTRUZIONE_DI_SISTEMA)
        return testo, "modello", nome_modello
    except Exception:
        return _testo_di_riserva(percorso, destinato_dermatologo), "riserva", None


def _leggi_paziente_e_questionario(connessione, paziente_id: int) -> dict:
    riga_paziente = connessione.execute(
        "SELECT nome, eta FROM pazienti WHERE id = ?", (paziente_id,)
    ).fetchone()
    if riga_paziente is None:
        raise ValueError(f"Nessun paziente trovato con id {paziente_id}")
    nome, eta = riga_paziente

    riga_questionario = connessione.execute(
        """SELECT fototipo, categoria_nei, familiarita_melanoma, melanoma_pregresso,
                  immunosoppressione, neo_cambiato
           FROM questionari WHERE paziente_id = ? ORDER BY id DESC LIMIT 1""",
        (paziente_id,),
    ).fetchone()
    if riga_questionario is None:
        raise ValueError(f"Nessun questionario trovato per il paziente {paziente_id}")

    fototipo, categoria_nei, familiarita, melanoma_pregresso, immunosoppressione, neo_cambiato = riga_questionario

    return {
        "nome": nome,
        "eta": eta,
        "fototipo": fototipo,
        "categoria_nei": categoria_nei,
        "familiarita_melanoma": bool(familiarita),
        "melanoma_pregresso": bool(melanoma_pregresso),
        "immunosoppressione": bool(immunosoppressione),
        "neo_cambiato": bool(neo_cambiato),
    }


def _decisione_sintetica(nome: str, priorita: str, percorso: str, destinato_dermatologo: bool) -> str:
    # Il nome del paziente è incluso direttamente nella decisione (non solo
    # nell'input) perché la pagina Log Agenti la usa per comporre un titolo
    # sintetico, leggibile a colpo d'occhio durante una presentazione.
    if percorso == "prevenzione":
        sintesi_percorso = "solo prevenzione"
    elif destinato_dermatologo:
        sintesi_percorso = "al dermatologo"
    else:
        sintesi_percorso = "percorso con foto"
    return f"{nome}: priorità {priorita.upper()}, {sintesi_percorso}"


def valuta_questionario(paziente_id: int) -> dict:
    """Punto di ingresso dell'agente ACCOGLIENZA: legge il questionario più
    recente del paziente, calcola priorità e percorso, apre un nuovo caso, genera
    il testo per il paziente (o usa un testo di riserva) e registra l'azione.

    Restituisce un dizionario con tutto il necessario per mostrare l'esito in
    interfaccia, senza bisogno di ulteriori query.
    """
    connessione = ottieni_connessione()
    try:
        dati = _leggi_paziente_e_questionario(connessione, paziente_id)

        # --- Decisione: SOLO codice Python, mai il modello linguistico. ---
        info_punteggio = calcola_punteggio_rischio_costituzionale(
            eta=dati["eta"],
            fototipo=dati["fototipo"],
            categoria_nei=dati["categoria_nei"],
            familiarita_melanoma=dati["familiarita_melanoma"],
            melanoma_pregresso=dati["melanoma_pregresso"],
            immunosoppressione=dati["immunosoppressione"],
        )
        info_percorso = decidi_percorso(info_punteggio["priorita"], dati["neo_cambiato"])

        priorita = info_punteggio["priorita"]
        percorso = info_percorso["percorso"]
        destinato_dermatologo = info_percorso["destinato_dermatologo"]
        motivo_completo = f"{info_punteggio['motivo']} {info_percorso['motivo']}"

        # --- Salvataggio del caso: avviene PRIMA di contattare il modello
        # linguistico, così la decisione clinica è al sicuro qualunque cosa
        # succeda nella chiamata a Gemini. ---
        oggi = date.today().isoformat()
        cursore = connessione.execute(
            """INSERT INTO casi (paziente_id, lesione_id, priorita, stato, data_apertura)
               VALUES (?, NULL, ?, ?, ?)""",
            (paziente_id, priorita, _stato_da_percorso(percorso, destinato_dermatologo), oggi),
        )
        caso_id = cursore.lastrowid
        connessione.commit()

        domanda = _costruisci_domanda(info_punteggio["motivo"], percorso, destinato_dermatologo, dati["neo_cambiato"])
        testo_paziente, fonte_testo, modello_usato = _genera_testo_e_fonte(domanda, percorso, destinato_dermatologo)

        data_testo = datetime.now().isoformat(timespec="seconds")
        connessione.execute(
            "UPDATE casi SET testo_paziente = ?, fonte_testo = ?, data_testo = ? WHERE id = ?",
            (testo_paziente, fonte_testo, data_testo, caso_id),
        )
        connessione.commit()
    finally:
        connessione.close()

    # --- Registro: sempre scritto, indipendentemente dall'esito della chiamata
    # al modello linguistico. Il modello effettivamente usato è incluso nel
    # motivo per tracciabilità: permette di capire dal log quanta quota si sta
    # consumando e su quale modello della catena. ---
    riassunto_questionario = (
        f"{dati['nome']}, {dati['eta']} anni, fototipo {dati['fototipo']}, "
        f"nei {dati['categoria_nei']}, familiarità {'sì' if dati['familiarita_melanoma'] else 'no'}, "
        f"melanoma pregresso {'sì' if dati['melanoma_pregresso'] else 'no'}, "
        f"immunosoppressione {'sì' if dati['immunosoppressione'] else 'no'}, "
        f"neo cambiato {'sì' if dati['neo_cambiato'] else 'no'}"
    )
    motivo_registro = motivo_completo
    if fonte_testo == "modello":
        motivo_registro += f" [Testo per il paziente generato dal modello {modello_usato}.]"
    else:
        motivo_registro += (
            " [Testo per il paziente generato con contenuto di riserva: modello linguistico non disponibile.]"
        )

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=riassunto_questionario,
        decisione=_decisione_sintetica(dati["nome"], priorita, percorso, destinato_dermatologo),
        motivo=motivo_registro,
        caso_id=caso_id,
    )

    return {
        "caso_id": caso_id,
        "paziente_id": paziente_id,
        "modello_usato": modello_usato,
        "nome_paziente": dati["nome"],
        "punteggio": info_punteggio["punteggio"],
        "priorita": priorita,
        "percorso": percorso,
        "destinato_dermatologo": destinato_dermatologo,
        "motivo": motivo_completo,
        "testo_paziente": testo_paziente,
        "fonte_testo": fonte_testo,
    }


def rigenera_testo_paziente(paziente_id: int) -> dict:
    """Rigenera il testo per il paziente sovrascrivendo quello salvato nell'ultimo
    caso aperto, SENZA aprire un nuovo caso: priorità e percorso non cambiano
    (dipendono solo dal questionario, non dalla formulazione del testo). Pensata
    per lo sviluppo e le prove, per verificare le istruzioni date al modello
    linguistico senza accumulare nuovi fascicoli per lo stesso paziente.
    """
    connessione = ottieni_connessione()
    try:
        dati = _leggi_paziente_e_questionario(connessione, paziente_id)

        riga_caso = connessione.execute(
            "SELECT id, priorita, stato FROM casi WHERE paziente_id = ? ORDER BY id DESC LIMIT 1",
            (paziente_id,),
        ).fetchone()
        if riga_caso is None:
            raise ValueError(
                f"Nessun caso esistente per il paziente {paziente_id}: usa prima 'Ottieni esito'."
            )
        caso_id, priorita, stato = riga_caso
        percorso, destinato_dermatologo = _percorso_da_stato(stato)

        # Il punteggio/motivo si ricalcola dal questionario (funzioni pure,
        # deterministiche): serve solo per comporre la domanda al modello, non
        # per decidere di nuovo priorità o percorso, che restano quelli salvati.
        info_punteggio = calcola_punteggio_rischio_costituzionale(
            eta=dati["eta"],
            fototipo=dati["fototipo"],
            categoria_nei=dati["categoria_nei"],
            familiarita_melanoma=dati["familiarita_melanoma"],
            melanoma_pregresso=dati["melanoma_pregresso"],
            immunosoppressione=dati["immunosoppressione"],
        )

        domanda = _costruisci_domanda(info_punteggio["motivo"], percorso, destinato_dermatologo, dati["neo_cambiato"])
        testo_paziente, fonte_testo, modello_usato = _genera_testo_e_fonte(domanda, percorso, destinato_dermatologo)

        data_testo = datetime.now().isoformat(timespec="seconds")
        connessione.execute(
            "UPDATE casi SET testo_paziente = ?, fonte_testo = ?, data_testo = ? WHERE id = ?",
            (testo_paziente, fonte_testo, data_testo, caso_id),
        )
        connessione.commit()
    finally:
        connessione.close()

    motivo_registro = "Rigenerazione manuale del testo per il paziente (sviluppo/test)."
    if fonte_testo == "modello":
        motivo_registro += f" Testo generato dal modello {modello_usato}."
    else:
        motivo_registro += " Testo generato con contenuto di riserva: modello linguistico non disponibile."

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=f"Rigenerazione testo per {dati['nome']} (caso #{caso_id})",
        decisione=f"{dati['nome']}: testo per il paziente rigenerato",
        motivo=motivo_registro,
        caso_id=caso_id,
    )

    return {
        "modello_usato": modello_usato,
        "caso_id": caso_id,
        "paziente_id": paziente_id,
        "nome_paziente": dati["nome"],
        "punteggio": info_punteggio["punteggio"],
        "priorita": priorita,
        "percorso": percorso,
        "destinato_dermatologo": destinato_dermatologo,
        "motivo": f"{info_punteggio['motivo']}",
        "testo_paziente": testo_paziente,
        "fonte_testo": fonte_testo,
    }
