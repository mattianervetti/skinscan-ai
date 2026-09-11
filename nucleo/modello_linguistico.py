"""
Modulo unico per parlare con il modello linguistico (Google Gemini).

Regola del progetto (vedi CLAUDE.md, sezione 4): SOLO questo file può importare
truststore e leggere GOOGLE_API_KEY. Nessun altro file del progetto deve farlo.
Questo modulo si occupa solo di comunicazione con il modello: non contiene
nessuna logica clinica o di business.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI


# Nome del modello Gemini da usare: cambialo qui se in futuro serve un'altra versione.
NOME_MODELLO = "gemini-2.5-flash"


# --- Configurazione SSL (necessaria in locale su Windows, non su Linux/Streamlit Cloud) ---
# truststore fa usare a Python il magazzino certificati del sistema operativo invece di
# quello "isolato" incluso in Python. Su Windows serve per aggirare antivirus/reti che
# ispezionano il traffico HTTPS. Su Linux (Streamlit Community Cloud) di solito non serve
# e potrebbe non essere necessario: per questo il fallimento non deve bloccare l'avvio.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception as errore_truststore:
    print(f"Avviso: configurazione SSL truststore non applicata ({errore_truststore}). "
          "Proseguo comunque: su Linux/Streamlit Cloud di solito non serve.")


# --- Lettura della chiave API dal file .env (solo per l'uso in locale) ---
# Percorso calcolato con pathlib, relativo alla cartella del progetto: funziona identico
# su Windows e su Linux, senza mai scrivere percorsi assoluti tipo C:\...
_CARTELLA_PROGETTO = Path(__file__).resolve().parent.parent
_PERCORSO_ENV = _CARTELLA_PROGETTO / ".env"
load_dotenv(dotenv_path=_PERCORSO_ENV)


_MESSAGGIO_CHIAVE_MANCANTE = (
    "Non riesco a trovare la chiave GOOGLE_API_KEY.\n"
    "Come sistemarlo:\n"
    "- Se sei in locale: apri il file .env nella cartella del progetto e scrivi\n"
    "  GOOGLE_API_KEY=la_tua_chiave_vera (senza spazi né virgolette).\n"
    "- Se l'app è pubblicata su Streamlit Community Cloud: apri le impostazioni\n"
    "  dell'app, sezione 'Secrets', e aggiungi GOOGLE_API_KEY = \"la_tua_chiave_vera\"."
)


def _ottieni_chiave_api() -> str:
    """Recupera la chiave API: prima prova i secrets di Streamlit (usati online),
    poi il file .env (usato in locale). Non fa crashare l'app se una fonte manca."""

    # 1. Prova prima i secrets di Streamlit (è così che funzionerà su Streamlit Community Cloud).
    try:
        import streamlit as st

        chiave = st.secrets.get("GOOGLE_API_KEY")
        if chiave:
            return chiave
    except Exception:
        # Nessun secrets.toml disponibile (es. in locale, o fuori da un'app Streamlit): va bene, si prova col .env.
        pass

    # 2. Altrimenti prova la variabile letta dal file .env.
    chiave = os.getenv("GOOGLE_API_KEY")
    if chiave and chiave != "incolla_qui_la_tua_chiave":
        return chiave

    # 3. Nessuna delle due fonti ha la chiave: fermiamoci con un messaggio chiaro.
    raise RuntimeError(_MESSAGGIO_CHIAVE_MANCANTE)


def _traduci_errore(errore: Exception) -> str:
    """Trasforma un errore tecnico della chiamata a Gemini in un messaggio comprensibile."""
    testo_errore = str(errore).lower()

    if "api key" in testo_errore or "api_key" in testo_errore or "invalid" in testo_errore or "permission" in testo_errore:
        return (
            "La chiave API sembra non valida. Controlla il valore di GOOGLE_API_KEY "
            "nel file .env (o nei Secrets di Streamlit Cloud) e verifica che sia stata "
            "copiata per intero, senza spazi extra."
        )

    if "quota" in testo_errore or "resource_exhausted" in testo_errore or "429" in testo_errore:
        return (
            "È stata esaurita la quota gratuita giornaliera del modello Gemini. "
            "Riprova più tardi (la quota si resetta ogni giorno) oppure controlla "
            "il limite nel tuo account Google AI Studio."
        )

    if any(parola in testo_errore for parola in ["ssl", "certificate", "connect", "timeout", "network", "connessione"]):
        return (
            "Problema di connessione di rete verso i server di Google (rete assente, "
            "instabile, o bloccata da firewall/antivirus/VPN). Controlla la connessione "
            "a Internet e riprova."
        )

    return f"Errore imprevisto nella chiamata al modello Gemini: {errore}"


def chiedi_al_modello(domanda: str, istruzione_di_sistema: str | None = None) -> str:
    """Fa una domanda al modello linguistico e restituisce la risposta come testo.

    Parametri:
        domanda: la domanda o richiesta da inviare al modello.
        istruzione_di_sistema: istruzione opzionale che definisce il comportamento
            del modello (es. "Rispondi sempre in italiano semplice").

    Solleva RuntimeError con un messaggio comprensibile in italiano se qualcosa va storto.
    """
    chiave_api = _ottieni_chiave_api()

    modello = ChatGoogleGenerativeAI(model=NOME_MODELLO, google_api_key=chiave_api)

    messaggi = []
    if istruzione_di_sistema:
        messaggi.append(("system", istruzione_di_sistema))
    messaggi.append(("human", domanda))

    try:
        risposta = modello.invoke(messaggi)
    except Exception as errore:
        raise RuntimeError(_traduci_errore(errore)) from errore

    return risposta.content
