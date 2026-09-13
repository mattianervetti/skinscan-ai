"""Pagina Dermatologo: coda dei casi in attesa di valutazione, ordinata per
priorità (agente INSTRADAMENTO). La scheda completa del caso (questionario,
foto, analisi, storico) e il meccanismo di decisione del dermatologo arrivano
nella Fase 3 (Supervisore)."""

import streamlit as st

from agenti.instradamento import ottieni_coda_dermatologo

_ICONA_PRIORITA = {"alta": "🔴", "media": "🟠", "bassa": "🟢"}


def mostra_pagina() -> None:
    st.title("Area Dermatologo")

    coda = ottieni_coda_dermatologo()

    if not coda:
        st.info("Nessun caso in coda al momento.")
        return

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
