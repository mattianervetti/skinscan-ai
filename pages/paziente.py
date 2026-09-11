"""Pagina Paziente: per ora solo un segnaposto onesto su cosa conterrà."""

import streamlit as st


def mostra_pagina() -> None:
    st.title("Area Paziente")

    st.info("Questa pagina è un segnaposto: le funzionalità non sono ancora implementate.")

    st.markdown(
        "Qui il paziente potrà:\n"
        "- iscriversi alla piattaforma;\n"
        "- compilare il questionario di valutazione del rischio;\n"
        "- scattare le foto guidate dei propri nei;\n"
        "- consultare gli esiti ricevuti;\n"
        "- vedere le notifiche;\n"
        "- consultare i prossimi controlli programmati."
    )
