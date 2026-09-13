"""
Modulo unico per parlare con il modello linguistico (Google Gemini).

Regola del progetto (vedi CLAUDE.md, sezione 4): SOLO questo file può importare
truststore, leggere GOOGLE_API_KEY e leggere DISATTIVA_MODELLO. Nessun altro
file del progetto deve farlo. Questo modulo si occupa solo di comunicazione con
il modello: non contiene nessuna logica clinica o di business.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ChatGoogleGenerativeAI viene importato più sotto, dentro chiedi_al_modello,
# non qui in cima al file: importarlo qui lo eseguirebbe SEMPRE, anche quando
# DISATTIVA_MODELLO=true, vanificando lo scopo dell'interruttore (lavorare
# sull'interfaccia senza toccare Gemini). Rilevante anche perché quell'import
# trascina una libreria nativa (uuid_utils) che su alcuni PC Windows può essere
# bloccata da un criterio di controllo delle applicazioni (Windows Defender
# Application Control/Smart App Control): con l'import rimandato, quel
# problema non impedisce più lo sviluppo a interruttore attivo.


# Catena di modelli da provare in ordine: se il primo esaurisce la quota
# giornaliera si passa automaticamente al successivo, senza che chi chiama se ne
# accorga. La quota gratuita di Google AI Studio è di 20 richieste al giorno PER
# SINGOLO MODELLO: avere più modelli in catena moltiplica la quota disponibile.
#
# NOTA: "gemini-2.5-flash-lite" e "gemini-3-flash" (i nomi originariamente
# previsti) non sono invocabili tramite l'API con questo account (errore 404,
# non di quota), pur comparendo nel pannello quote di AI Studio. Sostituiti con
# i corrispondenti verificati funzionanti: "gemini-3.5-flash-lite" (suggerito
# direttamente dall'errore di Google come sostituto) e "gemini-3-flash-preview"
# (unico nome realmente esposto dall'API per quella famiglia). Se in futuro
# "gemini-2.5-flash-lite"/"gemini-3-flash" tornassero disponibili, verificarli
# di nuovo prima di reinserirli.
CATENA_MODELLI = [
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
]


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


# --- Lettura della chiave API e delle impostazioni dal file .env (solo in locale) ---
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

_MESSAGGIO_MODELLO_DISATTIVATO = (
    "Chiamate al modello linguistico disattivate da configurazione "
    "(DISATTIVA_MODELLO=true nel file .env): in uso il testo di riserva."
)


def modello_disattivato() -> bool:
    """Indica se le chiamate al modello linguistico sono disattivate da
    configurazione (interruttore per lo sviluppo, vedi .env.example): se True,
    chi chiama userà sempre il testo di riserva, senza consumare quota.
    Funzione pubblica: altri file (es. la barra laterale) possono chiamarla per
    segnalarlo in interfaccia, senza dover leggere direttamente la variabile."""
    valore = os.getenv("DISATTIVA_MODELLO", "").strip().lower()
    return valore in ("1", "true", "si", "sì")


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


def _e_errore_di_quota(errore: Exception) -> bool:
    """Riconosce SOLO gli errori di quota esaurita (429/RESOURCE_EXHAUSTED): sono
    gli unici che devono far passare al modello successivo della catena. Un
    errore di rete o di chiave non deve far ciclare inutilmente su tutti."""
    testo_errore = str(errore).lower()
    return "quota" in testo_errore or "resource_exhausted" in testo_errore or "429" in testo_errore


def _traduci_errore(errore: Exception) -> str:
    """Trasforma un errore tecnico della chiamata a Gemini in un messaggio comprensibile."""
    testo_errore = str(errore).lower()

    if "api key" in testo_errore or "api_key" in testo_errore or "invalid" in testo_errore or "permission" in testo_errore:
        return (
            "La chiave API sembra non valida. Controlla il valore di GOOGLE_API_KEY "
            "nel file .env (o nei Secrets di Streamlit Cloud) e verifica che sia stata "
            "copiata per intero, senza spazi extra."
        )

    if _e_errore_di_quota(errore):
        return (
            "È stata esaurita la quota gratuita giornaliera per tutti i modelli "
            "Gemini disponibili nella catena di ripiego. Riprova domani (le quote "
            "si resettano giornalmente, sono 20 richieste al giorno per singolo "
            "modello) oppure controlla i limiti nel tuo account Google AI Studio."
        )

    if any(parola in testo_errore for parola in ["ssl", "certificate", "connect", "timeout", "network", "connessione"]):
        return (
            "Problema di connessione di rete verso i server di Google (rete assente, "
            "instabile, o bloccata da firewall/antivirus/VPN). Controlla la connessione "
            "a Internet e riprova."
        )

    return f"Errore imprevisto nella chiamata al modello Gemini: {errore}"


def _estrai_testo(contenuto) -> str:
    """Estrae il testo dalla risposta del modello, a prescindere dal formato.

    I modelli Gemini 2.x restituiscono il testo come stringa semplice; i modelli
    Gemini 3.x lo restituiscono come lista di blocchi strutturati
    (es. [{'type': 'text', 'text': '...'}]). Avere più formati nella stessa
    catena di ripiego richiede di gestirli entrambi qui, in un unico posto."""
    if isinstance(contenuto, str):
        return contenuto

    if isinstance(contenuto, list):
        parti = []
        for blocco in contenuto:
            if isinstance(blocco, dict) and blocco.get("type") == "text":
                parti.append(blocco.get("text", ""))
            elif isinstance(blocco, str):
                parti.append(blocco)
        return "".join(parti)

    return str(contenuto)


def chiedi_al_modello(domanda: str, istruzione_di_sistema: str | None = None) -> tuple[str, str]:
    """Fa una domanda al modello linguistico e restituisce (testo, nome_modello).

    Prova i modelli di CATENA_MODELLI in ordine: se un modello fallisce per
    quota esaurita passa automaticamente al successivo. Un errore di rete o di
    chiave non fa ciclare sugli altri modelli: viene sollevato subito.

    Parametri:
        domanda: la domanda o richiesta da inviare al modello.
        istruzione_di_sistema: istruzione opzionale che definisce il comportamento
            del modello (es. "Rispondi sempre in italiano semplice").

    Solleva RuntimeError con un messaggio comprensibile in italiano se qualcosa va storto
    (incluso il caso in cui le chiamate siano disattivate da configurazione).
    """
    if modello_disattivato():
        raise RuntimeError(_MESSAGGIO_MODELLO_DISATTIVATO)

    from langchain_google_genai import ChatGoogleGenerativeAI

    chiave_api = _ottieni_chiave_api()

    messaggi = []
    if istruzione_di_sistema:
        messaggi.append(("system", istruzione_di_sistema))
    messaggi.append(("human", domanda))

    ultimo_errore_di_quota: Exception | None = None
    for nome_modello in CATENA_MODELLI:
        try:
            modello = ChatGoogleGenerativeAI(model=nome_modello, google_api_key=chiave_api)
            risposta = modello.invoke(messaggi)
            return _estrai_testo(risposta.content), nome_modello
        except Exception as errore:
            if _e_errore_di_quota(errore):
                ultimo_errore_di_quota = errore
                continue  # prova il modello successivo della catena
            raise RuntimeError(_traduci_errore(errore)) from errore

    # Tutti i modelli della catena hanno esaurito la quota.
    raise RuntimeError(_traduci_errore(ultimo_errore_di_quota))
