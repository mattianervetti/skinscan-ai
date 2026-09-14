"""Pagina Dermatologo: coda dei casi in attesa di valutazione, ordinata per
priorità (agente INSTRADAMENTO); scheda completa del caso con la decisione
clinica del dermatologo (Fase 3, passo 3: agenti/decisione_dermatologo.py e
agenti/grafo_decisione_dermatologo.py); esiti istologici in attesa (agente
FOLLOW-UP)."""

import streamlit as st
from langgraph.checkpoint.sqlite import SqliteSaver

from agenti.decisione_dermatologo import (
    ETICHETTE_AZIONE,
    ottieni_casi_in_attesa_nuova_foto,
    ottieni_scheda_caso,
)
from agenti.followup import (
    carica_esito_istologico,
    ottieni_casi_in_attesa_di_esito_istologico,
    sollecita_esito_istologico,
)
from agenti.grafo import ottieni_connessione_stato_grafo
from agenti.grafo_decisione_dermatologo import (
    avvia_o_recupera_decisione,
    costruisci_grafo_decisione,
    invia_decisione,
)
from agenti.instradamento import ottieni_casi_scalati_a_operatore, ottieni_coda_dermatologo
from nucleo.regole_sicurezza import AZIONI_DERMATOLOGO_POSSIBILI
from nucleo.registro_audit import CLASSIFICAZIONI_ISTOLOGICHE_POSSIBILI, ETICHETTE_ISTOLOGICO

_ICONA_PRIORITA = {"alta": "🔴", "media": "🟠", "bassa": "🟢"}

_ETICHETTE_CLASSIFICAZIONE_ALGORITMO = {
    "sospetta": "Sospetta",
    "probabilmente_benigna": "Probabilmente benigna",
    "non_conclusiva": "Non conclusiva",
}


def mostra_pagina() -> None:
    st.title("Area Dermatologo")

    if "messaggio_followup" in st.session_state:
        st.success(st.session_state.pop("messaggio_followup"))

    caso_aperto = st.session_state.get("caso_aperto_dermatologo")
    if caso_aperto is not None:
        _mostra_scheda_caso(caso_aperto)
        return

    coda = ottieni_coda_dermatologo()

    if not coda:
        st.info("Nessun caso in coda al momento.")
    else:
        st.write(f"**{len(coda)} caso/i in coda**, dal più urgente:")

        for caso in coda:
            colonna_info, colonna_pulsante = st.columns([4, 1])
            with colonna_info:
                etichetta = (
                    f"{_ICONA_PRIORITA[caso['priorita']]} **{caso['nome_paziente']}** — "
                    f"priorità {caso['priorita'].upper()} — aperto il {caso['data_apertura']}"
                )
                if caso["qualita_foto_insufficiente"]:
                    etichetta += " — ⚠️ qualità foto insufficiente"
                st.write(etichetta)
            with colonna_pulsante:
                if st.button("📂 Apri scheda", key=f"apri_scheda_{caso['caso_id']}"):
                    st.session_state["caso_aperto_dermatologo"] = caso["caso_id"]
                    st.rerun()

    _mostra_sezione_scalati_a_operatore()
    _mostra_sezione_attesa_nuova_foto()
    _mostra_sezione_esiti_istologici_in_attesa()


def _mostra_scheda_caso(caso_id: int) -> None:
    """Scheda completa di un caso in coda: dati del questionario, foto
    accettata e precedente affiancate, esito del classificatore con l'avviso
    di simulazione nello stesso blocco, confronto storico, qualità
    dell'immagine, proposta del sistema e i 5 pulsanti di decisione. Apre (o
    ritrova, se già aperta in un rerun precedente) il grafo dedicato al tratto
    umano: il grafo si sospende qui, in attesa della scelta del dermatologo."""
    if st.button("← Torna alla coda"):
        del st.session_state["caso_aperto_dermatologo"]
        st.rerun()

    try:
        scheda = ottieni_scheda_caso(caso_id)
    except ValueError:
        # Un caso con "neo cambiato" entra in coda subito dopo il questionario
        # (agenti/accoglienza.py, invariato), prima ancora che il paziente
        # invii una foto: non c'è ancora nulla su cui il dermatologo possa
        # decidere. Messaggio informativo, non un errore della pagina.
        st.info("Il paziente non ha ancora inviato una foto per questo caso: non c'è ancora nulla da valutare.")
        return

    st.subheader(f"Scheda del caso — {scheda['nome_paziente']}, {scheda['eta']} anni")

    mostra_priorita = {"bassa": st.success, "media": st.warning, "alta": st.error}[scheda["priorita"]]
    mostra_priorita(f"Priorità: {scheda['priorita'].upper()} (punteggio {scheda['punteggio_rischio']})")
    st.caption(scheda["motivo_priorita"])
    if scheda["neo_cambiato"]:
        st.write("🔺 Il paziente ha dichiarato che un neo è cambiato di recente.")

    st.divider()
    st.write("**Fotografie**")
    colonna_precedente, colonna_corrente = st.columns(2)
    with colonna_precedente:
        st.caption("Foto precedente")
        if scheda["foto_precedente"] is not None:
            # width="stretch" per ENTRAMBE le foto (non solo questa): colonne
            # di uguale larghezza garantiscono che le due immagini siano
            # mostrate alla stessa dimensione, qualunque sia la risoluzione
            # originale del file — il confronto visivo perde senso se una
            # foto appare più piccola dell'altra.
            st.image(
                scheda["foto_precedente"]["dati"],
                caption=scheda["foto_precedente"]["data_scatto"],
                width="stretch",
            )
        else:
            st.write("Nessuna foto precedente per questa lesione.")
    with colonna_corrente:
        st.caption("Foto attuale")
        st.image(
            scheda["foto_corrente"]["dati"],
            caption=scheda["foto_corrente"]["data_scatto"],
            width="stretch",
        )

    if scheda["qualita_foto_insufficiente"]:
        st.warning(
            "⚠️ La foto attuale è stata accettata dopo 3 tentativi con qualità ancora "
            "insufficiente (regola di non esclusione dell'agente GUIDA ALLA FOTO)."
        )

    st.divider()
    st.write("**Esito del classificatore simulato**")
    analisi = scheda["analisi"]
    st.write(
        f"Classificazione: **{_ETICHETTE_CLASSIFICAZIONE_ALGORITMO[analisi['classificazione']]}** "
        f"— confidenza {analisi['confidenza']:.2f}"
    )
    st.caption(f"⚠️ {analisi['avviso_simulazione']}")
    if analisi["confronto_storico"]:
        st.write(f"Confronto con lo storico: {analisi['confronto_storico']}")

    st.divider()
    st.write("**Cosa propone il sistema**")
    st.info(f"{ETICHETTE_AZIONE[scheda['proposta_sistema']]} — {scheda['motivo_proposta']}")

    st.divider()
    st.write("**Decisione del dermatologo**")

    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo = costruisci_grafo_decisione(checkpointer=SqliteSaver(connessione))
        avvia_o_recupera_decisione(grafo, caso_id)

        # Pulsanti impilati a piena larghezza (non in colonne strette): le
        # etichette devono restare leggibili per intero, anche proiettate.
        # Tutti e 5 con lo stesso stile (nessun type="primary", nessuna
        # dimensione o posizione diversa): la proposta del sistema è già
        # scritta per esteso nel riquadro sopra, con le stesse identiche
        # parole dell'etichetta del pulsante corrispondente (ETICHETTE_AZIONE
        # è l'unica fonte per entrambi) — un indicatore anche sul pulsante
        # abbasserebbe il costo di essere d'accordo, l'inerzia che questo
        # passo vuole togliere (richiesta esplicita di Mattia).
        for azione in AZIONI_DERMATOLOGO_POSSIBILI:
            if st.button(ETICHETTE_AZIONE[azione], key=f"azione_{azione}_{caso_id}", width="stretch"):
                invia_decisione(grafo, caso_id, azione)
                st.session_state["messaggio_followup"] = (
                    f"Decisione registrata per {scheda['nome_paziente']}: {ETICHETTE_AZIONE[azione]}."
                )
                del st.session_state["caso_aperto_dermatologo"]
                st.rerun()
    finally:
        connessione.close()


def _mostra_sezione_scalati_a_operatore() -> None:
    """Elenco, separato e visivamente distinto dalla coda, dei casi scalati a
    un operatore umano: NON richiedono una valutazione clinica del
    dermatologo, ma una telefonata. Il messaggio già inviato al paziente
    promette che un operatore lo contatterà — questa sezione è dove quella
    promessa deve essere visibile a chi lavora, altrimenti nessuno la
    manterrebbe davvero (vedi CLAUDE.md)."""
    casi_scalati = ottieni_casi_scalati_a_operatore()
    if not casi_scalati:
        return

    st.divider()
    st.error(f"☎️ {len(casi_scalati)} caso/i da richiamare — non richiedono una valutazione clinica")

    for caso in casi_scalati:
        st.markdown(
            f"**{caso['nome_paziente']}** — {caso['motivo_escalation'] or 'motivo non disponibile'}  \n"
            f"Ultima azione: {caso['data_ultima_azione'] or 'n/d'} — "
            f"solleciti inviati: {caso['numero_solleciti']}"
        )


def _mostra_sezione_attesa_nuova_foto() -> None:
    """Elenco, separato e visivamente distinto dalla coda, dei casi per cui il
    dermatologo ha richiesto una nuova foto: NON richiedono una valutazione
    clinica ora, aspettano un'azione del paziente. st.info (blu), non
    st.warning: l'arancione di st.warning è lo stesso registro cromatico
    dell'icona 🟠 di priorità MEDIA nella coda clinica sopra, e potrebbe far
    leggere questa sezione come un'altra coda clinica — st.info è lo stesso
    stile già usato per "esiti istologici in attesa" qui sotto, un'altra lista
    puramente logistica, non clinica (passo 3.4, richiesta esplicita di
    Mattia). LIMITE APERTO (Fase 4, vedi CLAUDE.md): oggi non esiste ancora,
    dal lato paziente, un modo per ricaricare la foto di QUESTO caso specifico
    — per questo un caso qui resta visibile invece di sparire come se fosse
    stato gestito."""
    casi_in_attesa = ottieni_casi_in_attesa_nuova_foto()
    if not casi_in_attesa:
        return

    st.divider()
    st.info(
        f"📸 {len(casi_in_attesa)} caso/i in attesa che il paziente carichi una nuova foto — "
        "NON richiedono una valutazione clinica ora, aspettano un'azione del paziente"
    )
    for caso in casi_in_attesa:
        st.markdown(f"**{caso['nome_paziente']}** — richiesta il {caso['data_richiesta'] or 'n/d'}")


def _mostra_sezione_esiti_istologici_in_attesa() -> None:
    """Elenco dei casi con una biopsia richiesta e nessun esito istologico
    ancora caricato: per ciascuno, un modulo per caricare l'esito (scelto tra
    le 5 classificazioni predefinite, vedi nucleo/registro_audit.py) e un
    pulsante per segnalare che è passato altro tempo senza risposta dal
    laboratorio."""
    casi_in_attesa = ottieni_casi_in_attesa_di_esito_istologico()
    if not casi_in_attesa:
        return

    st.divider()
    st.info(f"🔬 {len(casi_in_attesa)} esito/i istologico/i in attesa")

    for caso in casi_in_attesa:
        st.markdown(
            f"**{caso['nome_paziente']}** — biopsia del {caso['data_ora_biopsia']} — "
            f"solleciti inviati finora: {caso['numero_solleciti']}"
        )

        # Selectbox e pulsante di invio DENTRO un st.form: senza un modulo, un
        # clic sul pulsante subito dopo aver cambiato la selezione rischia di
        # leggere il valore prima che la nuova selezione sia stata registrata
        # (ogni widget fuori da un form innesca il proprio rerun in modo
        # indipendente). Dentro un form, il valore della selectbox è letto
        # SOLO al momento dell'invio, in un unico passaggio atomico: è la
        # correzione strutturale al bug per cui l'esito salvato non
        # corrispondeva a quello scelto.
        with st.form(key=f"form_esito_{caso['caso_id']}", border=False):
            colonna_scelta, colonna_carica = st.columns([3, 1])
            with colonna_scelta:
                scelta = st.selectbox(
                    "Esito istologico",
                    options=CLASSIFICAZIONI_ISTOLOGICHE_POSSIBILI,
                    format_func=lambda valore: ETICHETTE_ISTOLOGICO[valore],
                    key=f"scelta_istologico_{caso['caso_id']}",
                    label_visibility="collapsed",
                )
            with colonna_carica:
                invia = st.form_submit_button("Carica esito", key=f"carica_istologico_{caso['caso_id']}")

        if invia:
            carica_esito_istologico(caso["caso_id"], scelta)
            st.session_state["messaggio_followup"] = (
                f"Esito registrato per {caso['nome_paziente']}: {ETICHETTE_ISTOLOGICO[scelta]}."
            )
            st.rerun()

        if st.button(
            "⏱️ Sollecita",
            key=f"sollecita_istologico_{caso['caso_id']}",
            help="Simula il passare del tempo senza un esito dal laboratorio.",
        ):
            sollecita_esito_istologico(caso["appuntamento_id"])
            st.rerun()
