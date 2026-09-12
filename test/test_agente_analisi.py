"""
Test dell'agente ANALISI: verifica il flusso completo su Marta, Giulia e Paolo,
e la resilienza senza modello linguistico.

Il test più importante è quello di Giulia: un esito rassicurante del
classificatore NON deve mai chiudere il caso quando il paziente ha dichiarato
che un neo è cambiato.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.database import inizializza_database, ottieni_connessione
from nucleo.dati_demo import genera_immagini_demo
from agenti.accoglienza import valuta_questionario
from agenti.guida_foto import valuta_foto
from agenti.analisi import analizza_caso

_VALORE_ORIGINALE_DISATTIVA_MODELLO = None


def setup_module(module):
    global _VALORE_ORIGINALE_DISATTIVA_MODELLO
    _VALORE_ORIGINALE_DISATTIVA_MODELLO = os.environ.get("DISATTIVA_MODELLO")
    os.environ["DISATTIVA_MODELLO"] = "true"
    inizializza_database()


def teardown_module(module):
    if _VALORE_ORIGINALE_DISATTIVA_MODELLO is None:
        os.environ.pop("DISATTIVA_MODELLO", None)
    else:
        os.environ["DISATTIVA_MODELLO"] = _VALORE_ORIGINALE_DISATTIVA_MODELLO


def _id_paziente(nome: str) -> int:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute("SELECT id FROM pazienti WHERE nome = ?", (nome,)).fetchone()
    finally:
        connessione.close()
    return riga[0]


def _apri_caso_con_foto_accettata(nome_paziente: str, chiave_immagine: str) -> int:
    percorsi = genera_immagini_demo()
    esito_questionario = valuta_questionario(_id_paziente(nome_paziente))
    caso_id = esito_questionario["caso_id"]
    valuta_foto(caso_id, percorsi[chiave_immagine].read_bytes())
    return caso_id


def test_marta_sospetta_variazione_rilevata_dermatologo():
    caso_id = _apri_caso_con_foto_accettata("Marta", "marta_nitida")

    esito = analizza_caso(caso_id)

    assert esito["classificazione"] == "sospetta"
    assert esito["destinato_dermatologo"] is True
    assert esito["confronto"] is not None
    assert esito["confronto"]["variazioni_rilevate"] is True


def test_giulia_rassicurante_ma_neo_cambiato_va_comunque_al_dermatologo():
    """Il test più importante: un esito benigno non deve mai chiudere il caso
    se il paziente ha dichiarato che un neo è cambiato."""
    caso_id = _apri_caso_con_foto_accettata("Giulia", "giulia_nitida")

    esito = analizza_caso(caso_id)

    assert esito["classificazione"] == "probabilmente_benigna"
    assert esito["destinato_dermatologo"] is True  # per il neo cambiato, non per l'esito
    assert esito["stato"] == "in_coda_dermatologo"


def test_paolo_non_conclusiva_va_al_dermatologo():
    caso_id = _apri_caso_con_foto_accettata("Paolo", "paolo_nitida")

    esito = analizza_caso(caso_id)

    assert esito["classificazione"] == "non_conclusiva"
    assert esito["destinato_dermatologo"] is True


def test_testo_paziente_non_rivela_mai_la_classificazione():
    caso_id = _apri_caso_con_foto_accettata("Giulia", "giulia_nitida")
    esito = analizza_caso(caso_id)

    testo_minuscolo = esito["testo_paziente"].lower()
    for parola_vietata in ["sospett", "benign", "non conclusiv", "confidenza"]:
        assert parola_vietata not in testo_minuscolo, f"Il testo per il paziente non deve contenere '{parola_vietata}'"


def test_funziona_anche_se_il_modello_non_e_raggiungibile():
    caso_id = _apri_caso_con_foto_accettata("Marta", "marta_nitida")

    with patch("agenti.analisi.chiedi_al_modello", side_effect=RuntimeError("errore simulato per il test")):
        esito = analizza_caso(caso_id)

    assert esito["destinato_dermatologo"] is True
    assert esito["fonte_testo"] == "riserva"
    assert len(esito["testo_paziente"].strip()) > 0


def test_esito_salvato_con_avviso_di_simulazione_nella_stessa_riga():
    caso_id = _apri_caso_con_foto_accettata("Paolo", "paolo_nitida")
    analizza_caso(caso_id)

    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            """SELECT ac.esito, ac.confidenza, ac.avviso_simulazione
               FROM analisi_classificatore ac
               JOIN foto_lesioni fl ON fl.id = ac.foto_id
               JOIN lesioni l ON l.id = fl.lesione_id
               JOIN casi c ON c.lesione_id = l.id
               WHERE c.id = ? ORDER BY ac.id DESC LIMIT 1""",
            (caso_id,),
        ).fetchone()
    finally:
        connessione.close()

    assert riga is not None
    esito_salvato, confidenza_salvata, avviso_salvato = riga
    assert esito_salvato == "non_conclusiva"
    assert confidenza_salvata is not None
    assert avviso_salvato is not None and "simulat" in avviso_salvato.lower()


if __name__ == "__main__":
    inizializza_database()

    test_marta_sospetta_variazione_rilevata_dermatologo()
    print("OK - Marta: sospetta, variazione rilevata, dermatologo")

    test_giulia_rassicurante_ma_neo_cambiato_va_comunque_al_dermatologo()
    print("OK - Giulia: esito rassicurante MA neo cambiato -> dermatologo comunque (test più importante)")

    test_paolo_non_conclusiva_va_al_dermatologo()
    print("OK - Paolo: non conclusiva -> dermatologo")

    test_testo_paziente_non_rivela_mai_la_classificazione()
    print("OK - il testo per il paziente non rivela mai la classificazione")

    test_funziona_anche_se_il_modello_non_e_raggiungibile()
    print("OK - agente resiliente: funziona anche se il modello linguistico fallisce")

    test_esito_salvato_con_avviso_di_simulazione_nella_stessa_riga()
    print("OK - esito salvato con l'avviso di simulazione nella stessa riga")

    print("\nTEST SUPERATO")
