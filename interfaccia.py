"""
Componenti dell'interfaccia condivisi da TUTTE le pagine dell'app: il disclaimer
obbligatorio e la barra laterale. Vengono richiamati una sola volta, dal punto di
ingresso app.py, prima di eseguire qualsiasi pagina: così nessuna pagina futura
può dimenticarsi di mostrarli, perché non è compito loro farlo.
"""

import streamlit as st

from nucleo.database import resetta_database

# Testo del disclaimer obbligatorio (vedi CLAUDE.md, sezione 3): deve comparire
# in modo visibile su ogni schermata dell'app, senza eccezioni.
TESTO_DISCLAIMER = "Prototipo dimostrativo – non è un dispositivo medico"


def mostra_disclaimer() -> None:
    """Mostra il disclaimer obbligatorio, ben visibile, in cima alla pagina."""
    st.warning(f"⚠️ {TESTO_DISCLAIMER}")


def mostra_barra_laterale(fase_corrente: str) -> None:
    """Mostra nella barra laterale la fase di sviluppo attuale e il pulsante
    per reimpostare la demo alla situazione di partenza."""
    with st.sidebar:
        st.caption(f"Fase di sviluppo attuale: {fase_corrente}")

        if st.button("Reimposta demo"):
            resetta_database()
            st.success("Demo reimpostata: dati ripristinati ai 4 pazienti iniziali.")
