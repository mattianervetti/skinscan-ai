"""Pagina Dermatologo: per ora solo un segnaposto onesto su cosa conterrà."""

import streamlit as st


def mostra_pagina() -> None:
    st.title("Area Dermatologo")

    st.info("Questa pagina è un segnaposto: le funzionalità non sono ancora implementate.")

    st.markdown(
        "Qui il dermatologo potrà:\n"
        "- vedere la coda dei casi ordinata per priorità;\n"
        "- aprire la scheda di un caso (questionario, foto, analisi, storico);\n"
        "- approvare o modificare la decisione proposta dal sistema."
    )
