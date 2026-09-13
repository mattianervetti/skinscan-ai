"""
Test dell'agente INSTRADAMENTO: coda per priorità, prenotazione della
televisita simulata, conferma, solleciti e scalo a un operatore umano dopo 2
solleciti senza risposta, prenotazione della biopsia.

Il test più importante è quello dei solleciti (scenario di Paolo nella demo:
non conferma la televisita, riceve 2 solleciti, poi viene scalato a un
operatore umano) — e, insieme a quello, la verifica che i solleciti avvengano
in momenti simulati progressivi (vedi nucleo/tempo_simulato.py): senza
quello, la sequenza mostrata al pubblico contraddirebbe le date registrate.

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
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.database import inizializza_database, ottieni_connessione
from nucleo.dati_demo import genera_immagini_demo
from nucleo.registro_azioni import elenca_azioni
from nucleo.tempo_simulato import avanza_data_simulata
from agenti.accoglienza import valuta_questionario
from agenti.guida_foto import valuta_foto
from agenti.analisi import analizza_caso
from agenti.instradamento import (
    GIORNI_AVANZAMENTO_PER_SOLLECITO_DEMO,
    NOME_AGENTE,
    conferma_appuntamento,
    instrada_caso,
    ottieni_casi_scalati_a_operatore,
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


def test_caso_scalato_esce_dalla_coda_ed_entra_nellelenco_operatore():
    """Requisito esplicito (vedi CLAUDE.md): un caso scalato a un operatore
    umano non deve più comparire nella coda ordinaria del dermatologo (non
    aspetta più una valutazione clinica) e deve comparire nell'elenco
    separato, con motivo, data dell'ultima azione e numero di solleciti."""
    caso_id = _apri_caso_destinato_al_dermatologo("Paolo", "paolo_nitida")
    appuntamento_id = instrada_caso(caso_id)["appuntamento_id"]

    assert caso_id in [caso["caso_id"] for caso in ottieni_coda_dermatologo()]
    assert caso_id not in [caso["caso_id"] for caso in ottieni_casi_scalati_a_operatore()]

    sollecita_appuntamento(appuntamento_id)
    sollecita_appuntamento(appuntamento_id)
    sollecita_appuntamento(appuntamento_id)  # scalo a operatore

    assert caso_id not in [caso["caso_id"] for caso in ottieni_coda_dermatologo()]

    casi_scalati = {caso["caso_id"]: caso for caso in ottieni_casi_scalati_a_operatore()}
    assert caso_id in casi_scalati
    caso_scalato = casi_scalati[caso_id]
    assert caso_scalato["nome_paziente"] == "Paolo"
    assert caso_scalato["numero_solleciti"] == 2
    assert caso_scalato["motivo_escalation"] is not None and "solleciti" in caso_scalato["motivo_escalation"]
    assert caso_scalato["data_ultima_azione"] is not None


def _data_invio_notifica_televisita(caso_id: int):
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT data_invio FROM notifiche WHERE caso_id = ? AND tipo = 'invito_televisita'",
            (caso_id,),
        ).fetchone()
    finally:
        connessione.close()
    return datetime.fromisoformat(riga[0])


def test_solleciti_producono_date_progressive_e_coerenti():
    """Requisito esplicito: la sequenza di Paolo (proposta -> sollecito 1 ->
    sollecito 2 -> scalo operatore) deve avere date simulate progressive, non
    tutte identiche all'istante reale in cui si clicca il pulsante demo — e
    devono cadere TUTTE prima della data dell'appuntamento proposto: un
    sollecito (o uno scalo a operatore) per un appuntamento già passato non
    avrebbe senso nel racconto della demo."""
    caso_id = _apri_caso_destinato_al_dermatologo("Paolo", "paolo_nitida")
    esito_instradamento = instrada_caso(caso_id)
    appuntamento_id = esito_instradamento["appuntamento_id"]
    data_appuntamento = datetime.fromisoformat(esito_instradamento["data_ora"])

    momento_proposta = _data_invio_notifica_televisita(caso_id)
    sollecita_appuntamento(appuntamento_id)
    momento_sollecito_1 = _data_invio_notifica_televisita(caso_id)
    sollecita_appuntamento(appuntamento_id)
    momento_sollecito_2 = _data_invio_notifica_televisita(caso_id)
    ultimo_esito = sollecita_appuntamento(appuntamento_id)  # scalo a operatore

    assert momento_sollecito_1 > momento_proposta
    assert momento_sollecito_2 > momento_sollecito_1
    assert (momento_sollecito_1 - momento_proposta).days == GIORNI_AVANZAMENTO_PER_SOLLECITO_DEMO
    assert (momento_sollecito_2 - momento_sollecito_1).days == GIORNI_AVANZAMENTO_PER_SOLLECITO_DEMO

    # Requisito esplicito: lo scalo a operatore deve avvenire PER CONTEGGIO
    # (2 solleciti), non perché la data è scaduta — e la sua data deve cadere
    # prima di quella dell'appuntamento.
    assert ultimo_esito["azione"] == "scalato_operatore"
    assert "solleciti" in ultimo_esito["motivo"]
    assert momento_sollecito_2 < data_appuntamento

    # Il registro delle azioni di INSTRADAMENTO per questo caso deve mostrare
    # la stessa progressione, in ordine cronologico crescente.
    azioni_instradamento = [
        azione for azione in reversed(elenca_azioni()) if azione["caso_id"] == caso_id and azione["agente"] == NOME_AGENTE
    ]
    date_registrate = [datetime.fromisoformat(azione["data_ora"]) for azione in azioni_instradamento]
    assert len(date_registrate) == 4  # proposta, sollecito 1, sollecito 2, scalo operatore
    assert date_registrate == sorted(date_registrate)
    assert len(set(date_registrate)) == len(date_registrate)  # nessuna data duplicata
    assert all(data < data_appuntamento for data in date_registrate)  # tutte prima dell'appuntamento


def test_scalo_operatore_se_la_data_dellappuntamento_e_scaduta():
    """Controllo indipendente dal conteggio dei solleciti: se la data
    simulata raggiunge quella dell'appuntamento proposto senza conferma, si
    scala subito a un operatore, anche al primo sollecito (senza aver ancora
    inviato i 2 solleciti previsti)."""
    caso_id = _apri_caso_destinato_al_dermatologo("Paolo", "paolo_nitida")
    appuntamento_id = instrada_caso(caso_id)["appuntamento_id"]

    avanza_data_simulata(30)  # ben oltre la data dell'appuntamento proposto

    esito = sollecita_appuntamento(appuntamento_id)

    assert esito["azione"] == "scalato_operatore"
    assert "scaduta" in esito["motivo"].lower() or "raggiunta" in esito["motivo"].lower()
    assert ottieni_stato_instradamento(caso_id)["stato_appuntamento"] == "scalato_operatore"
    assert ottieni_stato_instradamento(caso_id)["numero_solleciti"] == 0  # scalato senza nessun sollecito inviato


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

    test_caso_scalato_esce_dalla_coda_ed_entra_nellelenco_operatore()
    print("OK - un caso scalato esce dalla coda ordinaria ed entra nell'elenco per l'operatore")

    test_solleciti_producono_date_progressive_e_coerenti()
    print("OK - i solleciti e lo scalo a operatore hanno date simulate progressive e coerenti")

    test_scalo_operatore_se_la_data_dellappuntamento_e_scaduta()
    print("OK - se la data dell'appuntamento è scaduta si scala subito, anche senza 2 solleciti")

    test_sollecito_non_fa_nulla_su_appuntamento_gia_confermato()
    print("OK - nessun sollecito su un appuntamento già confermato")

    test_prenota_biopsia()
    print("OK - prenota_biopsia prenota presso il centro convenzionato simulato")

    print("\nTEST SUPERATO")
