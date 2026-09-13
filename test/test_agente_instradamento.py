"""
Test dell'agente INSTRADAMENTO: coda per priorità, prenotazione della
televisita simulata, conferma, solleciti e scalo a un operatore umano dopo 2
solleciti senza risposta, prenotazione della biopsia.

Il test più importante è quello dei solleciti (scenario di Paolo nella demo:
non conferma la televisita, riceve 2 solleciti, poi viene scalato a un
operatore umano).

Questo file non fa MAI chiamate reali al modello linguistico (vedi CLAUDE.md,
sezione 11): il modello è disattivato subito qui sotto, prima di importare
qualunque modulo del progetto. Serve perché aprire un caso fino allo stato
'in_coda_dermatologo' (vedi _apri_caso_destinato_al_dermatologo) passa anche
per gli Agenti ACCOGLIENZA, GUIDA ALLA FOTO e ANALISI, che il modello lo
userebbero davvero se non fosse disattivato. Per una vera chiamata a Gemini
vedi test/verifica_connessione_gemini.py (da lanciare a parte, su richiesta).
"""

import os

os.environ["DISATTIVA_MODELLO"] = "true"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.database import inizializza_database, ottieni_connessione
from nucleo.dati_demo import genera_immagini_demo
from agenti.accoglienza import valuta_questionario
from agenti.guida_foto import valuta_foto
from agenti.analisi import analizza_caso
from agenti.instradamento import (
    conferma_appuntamento,
    instrada_caso,
    ottieni_coda_dermatologo,
    ottieni_stato_instradamento,
    prenota_biopsia,
    sollecita_appuntamento,
)


def setup_module(module):
    inizializza_database()


def _id_paziente(nome: str) -> int:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute("SELECT id FROM pazienti WHERE nome = ?", (nome,)).fetchone()
    finally:
        connessione.close()
    return riga[0]


def _apri_caso_destinato_al_dermatologo(nome_paziente: str, chiave_immagine: str) -> int:
    """Porta un caso fino allo stato 'in_coda_dermatologo' passando per
    ACCOGLIENZA, GUIDA ALLA FOTO e ANALISI, come farebbe l'app."""
    percorsi = genera_immagini_demo()
    esito_questionario = valuta_questionario(_id_paziente(nome_paziente))
    caso_id = esito_questionario["caso_id"]
    valuta_foto(caso_id, percorsi[chiave_immagine].read_bytes())
    esito_analisi = analizza_caso(caso_id)
    assert esito_analisi["destinato_dermatologo"] is True
    return caso_id


def test_coda_ordinata_per_priorita():
    # Marta: priorità alta dal punteggio. Giulia: priorità bassa dal punteggio,
    # ma il neo cambiato la manda comunque in coda. Verifica che, in coda,
    # Marta comunque preceda Giulia nonostante entrambe siano destinate al
    # dermatologo.
    valuta_questionario(_id_paziente("Marta"))
    valuta_questionario(_id_paziente("Giulia"))

    coda = ottieni_coda_dermatologo()
    nomi_in_coda = [caso["nome_paziente"] for caso in coda]
    assert "Marta" in nomi_in_coda and "Giulia" in nomi_in_coda
    assert nomi_in_coda.index("Marta") < nomi_in_coda.index("Giulia")


def test_instrada_caso_crea_appuntamento_e_notifica():
    caso_id = _apri_caso_destinato_al_dermatologo("Paolo", "paolo_nitida")

    esito = instrada_caso(caso_id)

    assert esito["gia_instradato"] is False
    assert esito["stato_appuntamento"] == "proposto"

    connessione = ottieni_connessione()
    try:
        appuntamento = connessione.execute(
            "SELECT tipo, stato FROM appuntamenti WHERE id = ?", (esito["appuntamento_id"],)
        ).fetchone()
        notifica = connessione.execute(
            "SELECT tipo, confermata, numero_solleciti FROM notifiche WHERE caso_id = ?", (caso_id,)
        ).fetchone()
    finally:
        connessione.close()

    assert appuntamento == ("televisita", "proposto")
    assert notifica == ("invito_televisita", 0, 0)


def test_instrada_caso_e_idempotente():
    caso_id = _apri_caso_destinato_al_dermatologo("Paolo", "paolo_nitida")

    primo_esito = instrada_caso(caso_id)
    secondo_esito = instrada_caso(caso_id)

    assert secondo_esito["gia_instradato"] is True
    assert secondo_esito["appuntamento_id"] == primo_esito["appuntamento_id"]


def test_instrada_caso_fallisce_se_non_destinato_al_dermatologo():
    caso_id = valuta_questionario(_id_paziente("Luca"))["caso_id"]  # rischio basso, solo prevenzione

    try:
        instrada_caso(caso_id)
        assert False, "Doveva sollevare ValueError per un caso non destinato al dermatologo"
    except ValueError:
        pass


def test_conferma_appuntamento():
    caso_id = _apri_caso_destinato_al_dermatologo("Paolo", "paolo_nitida")
    esito_instradamento = instrada_caso(caso_id)

    conferma_appuntamento(esito_instradamento["appuntamento_id"])

    info = ottieni_stato_instradamento(caso_id)
    assert info["stato_appuntamento"] == "confermato"
    assert info["confermata"] is True


def test_solleciti_poi_scalo_operatore():
    """Scenario di Paolo nella demo: nessuna conferma, 2 solleciti, poi scalo
    a un operatore umano."""
    caso_id = _apri_caso_destinato_al_dermatologo("Paolo", "paolo_nitida")
    appuntamento_id = instrada_caso(caso_id)["appuntamento_id"]

    primo_sollecito = sollecita_appuntamento(appuntamento_id)
    assert primo_sollecito["azione"] == "sollecito_inviato"
    assert ottieni_stato_instradamento(caso_id)["numero_solleciti"] == 1
    assert ottieni_stato_instradamento(caso_id)["stato_appuntamento"] == "proposto"

    secondo_sollecito = sollecita_appuntamento(appuntamento_id)
    assert secondo_sollecito["azione"] == "sollecito_inviato"
    assert ottieni_stato_instradamento(caso_id)["numero_solleciti"] == 2
    assert ottieni_stato_instradamento(caso_id)["stato_appuntamento"] == "proposto"

    terzo_sollecito = sollecita_appuntamento(appuntamento_id)
    assert terzo_sollecito["azione"] == "scalato_operatore"
    assert ottieni_stato_instradamento(caso_id)["stato_appuntamento"] == "scalato_operatore"


def test_sollecito_non_fa_nulla_su_appuntamento_gia_confermato():
    caso_id = _apri_caso_destinato_al_dermatologo("Paolo", "paolo_nitida")
    appuntamento_id = instrada_caso(caso_id)["appuntamento_id"]
    conferma_appuntamento(appuntamento_id)

    esito = sollecita_appuntamento(appuntamento_id)

    assert esito["azione"] == "nessuna"
    assert ottieni_stato_instradamento(caso_id)["stato_appuntamento"] == "confermato"


def test_prenota_biopsia():
    caso_id = _apri_caso_destinato_al_dermatologo("Paolo", "paolo_nitida")

    esito = prenota_biopsia(caso_id)

    connessione = ottieni_connessione()
    try:
        appuntamento = connessione.execute(
            "SELECT tipo, stato, centro FROM appuntamenti WHERE id = ?", (esito["appuntamento_id"],)
        ).fetchone()
    finally:
        connessione.close()

    assert appuntamento[0] == "biopsia"
    assert appuntamento[1] == "proposto"
    assert appuntamento[2] is not None and "convenzionato" in appuntamento[2].lower()


if __name__ == "__main__":
    inizializza_database()

    test_coda_ordinata_per_priorita()
    print("OK - la coda del dermatologo è ordinata per priorità")

    test_instrada_caso_crea_appuntamento_e_notifica()
    print("OK - instrada_caso crea appuntamento (televisita) e notifica")

    test_instrada_caso_e_idempotente()
    print("OK - instrada_caso non duplica l'appuntamento se richiamato due volte")

    test_instrada_caso_fallisce_se_non_destinato_al_dermatologo()
    print("OK - instrada_caso rifiuta un caso non destinato al dermatologo")

    test_conferma_appuntamento()
    print("OK - conferma_appuntamento aggiorna appuntamento e notifica")

    test_solleciti_poi_scalo_operatore()
    print("OK - dopo 2 solleciti senza conferma il caso è scalato a un operatore umano (scenario Paolo)")

    test_sollecito_non_fa_nulla_su_appuntamento_gia_confermato()
    print("OK - nessun sollecito su un appuntamento già confermato")

    test_prenota_biopsia()
    print("OK - prenota_biopsia prenota presso il centro convenzionato simulato")

    print("\nTEST SUPERATO")
