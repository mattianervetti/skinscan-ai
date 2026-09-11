"""Pagina Home: presentazione del progetto e delle tre sezioni dell'app."""

import streamlit as st


def mostra_pagina() -> None:
    st.title("SkinScan AI")

    st.markdown(
        "**SkinScan AI** è un prototipo dimostrativo di piattaforma di prevenzione "
        "dermatologica da casa: il paziente compila un questionario, scatta foto guidate "
        "dei propri nei e riceve un esito. Se necessario, viene messo in contatto con un "
        "dermatologo per una televisita. Solo se il dermatologo lo ritiene necessario, il "
        "paziente si reca fisicamente in un centro convenzionato per una biopsia."
    )

    st.subheader("Le tre sezioni dell'app")
    st.markdown(
        "- **Paziente** — iscrizione, questionario, scatto guidato delle foto, esiti, "
        "notifiche, prossimi controlli.\n"
        "- **Dermatologo** — coda dei casi per priorità, scheda del singolo caso, decisione.\n"
        "- **Log agenti** — sequenza delle azioni compiute dagli agenti automatici."
    )

    st.info(
        "In questa fase le pagine sono segnaposto: mostrano solo cosa conterranno. "
        "Le funzionalità vere arriveranno nelle prossime fasi del progetto."
    )
