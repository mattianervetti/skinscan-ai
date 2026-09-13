"""
Test della pagina Dermatologo (pages/dermatologo.py) con streamlit.testing.v1,
non solo delle funzioni dell'agente: un bug reale è stato trovato qui, non
nell'agente. La selectbox dell'esito istologico e il pulsante "Carica esito"
NON erano dentro un modulo (st.form): un clic sul pulsante poteva leggere il
valore della selectbox prima che la nuova selezione fosse stata registrata,
salvando un esito diverso da quello scelto — la pagina non si è mai accorta
dell'errore, e il Registro di Audit ha mostrato dati falsi. Corretto
raggruppando selectbox e pulsante in un st.form: dentro un form, il valore
viene letto SOLO al momento dell'invio, in un unico passaggio atomico.

Questo file non fa MAI chiamate reali al modello linguistico (vedi CLAUDE.md,
sezione 11): il modello è disattivato subito qui sotto, prima di importare
qualunque modulo del progetto.
"""

import os

os.environ["DISATTIVA_MODELLO"] = "true"

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest

from nucleo.database import inizializza_database, ottieni_connessione
from nucleo.dati_demo import genera_immagini_demo
from nucleo.registro_audit import CLASSIFICAZIONI_ISTOLOGICHE_POSSIBILI
from agenti.accoglienza import valuta_questionario
from agenti.guida_foto import valuta_foto
from agenti.analisi import analizza_caso
from agenti.instradamento import instrada_caso, prenota_biopsia


_percorso_script_pagina = None


def setup_module(module):
    inizializza_database()

    # Un unico file-script temporaneo per tutto il modulo (non uno per
    # AppTest): ogni test qui chiama app.run() più volte sullo STESSO AppTest
    # (una volta per il render iniziale, una dopo l'interazione) e AppTest
    # rilegge il file a ogni run() — cancellarlo dopo il primo run rompe il
    # secondo con FileNotFoundError.
    global _percorso_script_pagina
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False
    ) as f:
        f.write("from pages.dermatologo import mostra_pagina\nmostra_pagina()\n")
        _percorso_script_pagina = f.name


def teardown_module(module):
    if _percorso_script_pagina is not None:
        os.unlink(_percorso_script_pagina)


def _id_paziente(nome: str) -> int:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute("SELECT id FROM pazienti WHERE nome = ?", (nome,)).fetchone()
    finally:
        connessione.close()
    return riga[0]


def _apri_caso_in_attesa_di_esito(nome_paziente: str, chiave_immagine: str) -> int:
    """Porta un caso fino alla biopsia richiesta (in attesa di esito), come
    farebbe il dermatologo dall'interfaccia."""
    percorsi = genera_immagini_demo()
    caso_id = valuta_questionario(_id_paziente(nome_paziente))["caso_id"]
    valuta_foto(caso_id, percorsi[chiave_immagine].read_bytes())
    esito_analisi = analizza_caso(caso_id)
    assert esito_analisi["destinato_dermatologo"] is True
    instrada_caso(caso_id)
    prenota_biopsia(caso_id)
    return caso_id


def _esegui_pagina_dermatologo() -> AppTest:
    app = AppTest.from_file(_percorso_script_pagina)
    app.run(timeout=30)
    return app


def _classificazione_salvata(caso_id: int) -> str:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT classificazione FROM esiti_istologici WHERE caso_id = ?", (caso_id,)
        ).fetchone()
    finally:
        connessione.close()
    assert riga is not None, f"Nessun esito istologico salvato per il caso {caso_id}"
    return riga[0]


def test_ogni_classificazione_selezionata_e_quella_salvata():
    """Requisito esplicito: per ciascuna delle 5 classificazioni possibili,
    selezionarla nella pagina e inviare il modulo deve salvare ESATTAMENTE
    quella scelta — mai un'altra (era il bug: si salvava sempre 'benigno',
    la prima opzione del menu, indipendentemente dalla selezione)."""
    for classificazione in CLASSIFICAZIONI_ISTOLOGICHE_POSSIBILI:
        caso_id = _apri_caso_in_attesa_di_esito("Paolo", "paolo_nitida")

        app = _esegui_pagina_dermatologo()
        assert not app.exception, f"Eccezione nella pagina Dermatologo: {app.exception}"

        selectbox = app.selectbox(key=f"scelta_istologico_{caso_id}")
        selectbox.select(classificazione)
        pulsante_carica = app.button(key=f"carica_istologico_{caso_id}")
        pulsante_carica.click()
        app.run(timeout=30)

        assert not app.exception, f"Eccezione dopo l'invio del modulo: {app.exception}"
        assert _classificazione_salvata(caso_id) == classificazione


def test_selezione_e_invio_ravvicinati_non_causano_una_corsa_critica():
    """Impostare la selezione e cliccare 'Carica esito' PRIMA di un solo run
    (la sequenza più a rischio di corsa critica tra i due widget) deve
    comunque salvare il valore selezionato: il modulo (st.form) rende la
    lettura della selectbox atomica al momento dell'invio."""
    caso_id = _apri_caso_in_attesa_di_esito("Paolo", "paolo_nitida")

    app = _esegui_pagina_dermatologo()

    app.selectbox(key=f"scelta_istologico_{caso_id}").set_value("melanoma_invasivo")
    app.button(key=f"carica_istologico_{caso_id}").click()
    app.run(timeout=30)

    assert not app.exception
    assert _classificazione_salvata(caso_id) == "melanoma_invasivo"


def test_messaggio_di_conferma_e_resto_della_pagina_dopo_il_caricamento():
    """Dopo il caricamento: un messaggio di conferma con paziente ed esito, e
    il resto della pagina (qui: la coda con un altro caso) resta visibile —
    non deve svuotarsi né sparire (era il secondo bug segnalato)."""
    valuta_questionario(_id_paziente("Giulia"))  # resta in coda ordinaria
    caso_marta = _apri_caso_in_attesa_di_esito("Marta", "marta_nitida")

    app = _esegui_pagina_dermatologo()
    app.selectbox(key=f"scelta_istologico_{caso_marta}").select("melanoma_in_situ")
    app.button(key=f"carica_istologico_{caso_marta}").click()
    app.run(timeout=30)

    assert not app.exception

    messaggi_conferma = [el.value for el in app.get("success")]
    assert any("Marta" in messaggio and "Melanoma in situ" in messaggio for messaggio in messaggi_conferma)

    testo_pagina = " ".join(el.value for el in app.get("markdown"))
    assert "Giulia" in testo_pagina  # la coda con l'altro caso non è sparita


if __name__ == "__main__":
    setup_module(None)

    test_ogni_classificazione_selezionata_e_quella_salvata()
    print("OK - per ciascuna delle 5 classificazioni, il valore selezionato è quello salvato")

    test_selezione_e_invio_ravvicinati_non_causano_una_corsa_critica()
    print("OK - selezione e invio ravvicinati non causano una corsa critica")

    test_messaggio_di_conferma_e_resto_della_pagina_dopo_il_caricamento()
    print("OK - messaggio di conferma mostrato, il resto della pagina non sparisce")

    teardown_module(None)
    print("\nTEST SUPERATO")
