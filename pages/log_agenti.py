"""Pagina Log Agenti: mostra le azioni registrate dagli agenti, più recenti prima.

Il titolo di ogni voce è pensato per essere comprensibile a colpo d'occhio durante
una presentazione dal vivo: riassume già data/ora, agente e decisione (che include
il nome del paziente). Il dettaglio completo resta nella parte espandibile.
"""

from datetime import datetime

import streamlit as st

from nucleo.registro_azioni import elenca_azioni


def _formatta_data_ora(data_ora_iso: str) -> str:
    try:
        return datetime.fromisoformat(data_ora_iso).strftime("%d/%m %H:%M")
    except ValueError:
        return data_ora_iso


def mostra_pagina() -> None:
    st.title("Log Agenti")

    azioni = elenca_azioni()

    if not azioni:
        st.info("Nessuna azione registrata finora. Vai nella pagina Paziente e ottieni un esito per vederne una qui.")
        return

    st.write(f"Azioni registrate: {len(azioni)} (dalla più recente)")

    for azione in azioni:
        timestamp = _formatta_data_ora(azione["data_ora"])
        titolo = f"{timestamp} — {azione['agente']} — {azione['decisione']}"
        with st.expander(titolo):
            st.write(f"**Input ricevuto:** {azione['input']}")
            st.write(f"**Motivo:** {azione['motivo']}")
