"""Pagina Log Agenti: per ora solo un segnaposto onesto su cosa conterrà."""

import streamlit as st


def mostra_pagina() -> None:
    st.title("Log Agenti")

    st.info("Questa pagina è un segnaposto: le funzionalità non sono ancora implementate.")

    st.markdown(
        "Qui sarà visibile, in ordine cronologico, la sequenza delle azioni compiute "
        "da ciascun agente automatico: quale agente ha agito, con quale input, quale "
        "decisione ha preso e per quale motivo."
    )
