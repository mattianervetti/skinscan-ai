"""Pagina Dermatologo: coda dei casi in attesa di valutazione, ordinata per
priorità (agente INSTRADAMENTO); richiesta di biopsia ed esiti istologici in
attesa (agente FOLLOW-UP). La scheda completa del caso (questionario, foto,
analisi, storico) e il meccanismo di intervento umano (human-in-the-loop) di
LangGraph arrivano nella Fase 3 (Supervisore) — vedi la nota su "Richiedi
biopsia" più sotto."""

import streamlit as st

from agenti.followup import (
    carica_esito_istologico,
    ottieni_casi_in_attesa_di_esito_istologico,
    sollecita_esito_istologico,
)
from agenti.instradamento import ottieni_casi_scalati_a_operatore, ottieni_coda_dermatologo, prenota_biopsia
from nucleo.registro_audit import CLASSIFICAZIONI_ISTOLOGICHE_POSSIBILI, ETICHETTE_ISTOLOGICO

_ICONA_PRIORITA = {"alta": "🔴", "media": "🟠", "bassa": "🟢"}


def mostra_pagina() -> None:
    st.title("Area Dermatologo")

    if "messaggio_followup" in st.session_state:
        st.success(st.session_state.pop("messaggio_followup"))

    coda = ottieni_coda_dermatologo()

    if not coda:
        st.info("Nessun caso in coda al momento.")
    else:
        st.write(f"**{len(coda)} caso/i in coda**, dal più urgente:")

        for caso in coda:
            etichetta = (
                f"{_ICONA_PRIORITA[caso['priorita']]} **{caso['nome_paziente']}** — "
                f"priorità {caso['priorita'].upper()} — aperto il {caso['data_apertura']}"
            )
            if caso["qualita_foto_insufficiente"]:
                etichetta += " — ⚠️ qualità foto insufficiente"
            st.write(etichetta)

            if st.button(
                "📋 Richiedi biopsia",
                key=f"richiedi_biopsia_{caso['caso_id']}",
                help=(
                    "Decisione clinica del dermatologo: prenota una biopsia presso il "
                    "centro convenzionato. In Fase 3 questa azione sarà collegata al "
                    "meccanismo di intervento umano (human-in-the-loop) di LangGraph; "
                    "il pulsante e la decisione restano gli stessi."
                ),
            ):
                prenota_biopsia(caso["caso_id"])
                st.rerun()

        st.caption(
            "La scheda completa del caso (questionario, foto, analisi, storico) sarà "
            "aggiunta nella Fase 3."
        )

    _mostra_sezione_scalati_a_operatore()
    _mostra_sezione_esiti_istologici_in_attesa()


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
