"""
Punto di ingresso dell'applicazione Streamlit SkinScan AI.

Questo è l'UNICO file che decide quale pagina mostrare (st.navigation) e che
richiama disclaimer e barra laterale PRIMA di eseguire la pagina scelta: così
nessuna pagina futura può dimenticarsi di mostrarli, perché non è compito loro.
"""

import streamlit as st

from nucleo.database import inizializza_database
from interfaccia import mostra_barra_laterale, mostra_disclaimer
from pages.home import mostra_pagina as pagina_home
from pages.paziente import mostra_pagina as pagina_paziente
from pages.dermatologo import mostra_pagina as pagina_dermatologo
from pages.log_agenti import mostra_pagina as pagina_log_agenti

FASE_SVILUPPO_CORRENTE = "Fase 1 — scheletro dell'app (pagine segnaposto, nessuna funzionalità)"

st.set_page_config(page_title="SkinScan AI")


@st.cache_resource
def _inizializza_database_una_sola_volta() -> None:
    # @st.cache_resource fa eseguire questa funzione una sola volta per processo,
    # non a ogni rerun dello script (Streamlit riesegue lo script a ogni interazione).
    # inizializza_database() crea le tabelle se mancano e ricarica i dati demo se il
    # database è vuoto: necessario perché su Streamlit Community Cloud il disco viene
    # azzerato a ogni riavvio dell'app.
    inizializza_database()


_inizializza_database_una_sola_volta()

pagina_selezionata = st.navigation(
    [
        # url_path esplicito: le funzioni si chiamano tutte "mostra_pagina", quindi
        # Streamlit non può derivare da sole un indirizzo univoco per ciascuna.
        st.Page(pagina_home, title="Home", url_path="home", default=True),
        st.Page(pagina_paziente, title="Paziente", url_path="paziente"),
        st.Page(pagina_dermatologo, title="Dermatologo", url_path="dermatologo"),
        st.Page(pagina_log_agenti, title="Log agenti", url_path="log-agenti"),
    ]
)

# Disclaimer e barra laterale mostrati SEMPRE, prima di eseguire la pagina scelta.
mostra_disclaimer()
mostra_barra_laterale(FASE_SVILUPPO_CORRENTE)

pagina_selezionata.run()
