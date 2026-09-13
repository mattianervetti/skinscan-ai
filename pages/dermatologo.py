"""Pagina Dermatologo: coda dei casi in attesa di valutazione, ordinata per
priorità (agente INSTRADAMENTO). La scheda completa del caso (questionario,
foto, analisi, storico) e il meccanismo di decisione del dermatologo arrivano
nella Fase 3 (Supervisore)."""

import streamlit as st

from agenti.instradamento import ottieni_casi_scalati_a_operatore, ottieni_coda_dermatologo

_ICONA_PRIORITA = {"alta": "🔴", "media": "🟠", "bassa": "🟢"}


def mostra_pagina() -> None:
    st.title("Area Dermatologo")

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

        st.caption(
            "La scheda completa del caso (questionario, foto, analisi, storico) e la "
            "decisione del dermatologo saranno aggiunte nella Fase 3."
        )

    _mostra_sezione_scalati_a_operatore()


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
