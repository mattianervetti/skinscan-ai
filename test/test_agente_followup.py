"""
Test dell'agente FOLLOW-UP: caricamento dell'esito istologico, confronto con
il classificatore registrato nel registro di audit, sollecito quando l'esito
non arriva, e programmazione del prossimo controllo periodico.

Il test più importante è quello di Giulia: analisi rassicurante ma neo
dichiarato cambiato — l'esito maligno deve essere contato come "recuperato da
una regola di sicurezza", MAI come falso negativo (vedi CLAUDE.md e
test/test_registro_audit.py per la stessa verifica sulla funzione pura).

Questo file non fa MAI chiamate reali al modello linguistico (vedi CLAUDE.md,
sezione 11): il modello è disattivato subito qui sotto, prima di importare
qualunque modulo del progetto — necessario perché arrivare fino alla biopsia
passa anche per gli Agenti ACCOGLIENZA, GUIDA ALLA FOTO e ANALISI.
"""

import os

os.environ["DISATTIVA_MODELLO"] = "true"

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.database import inizializza_database, ottieni_connessione
from nucleo.dati_demo import genera_immagini_demo
from nucleo.registro_audit import CATEGORIA_CONCORDANZA, CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA
from nucleo.regole_sicurezza import GIORNI_CONTROLLO_BREVE
from nucleo.tempo_simulato import ottieni_data_simulata
from agenti.accoglienza import valuta_questionario
from agenti.guida_foto import valuta_foto
from agenti.analisi import analizza_caso
from agenti.instradamento import instrada_caso, ottieni_coda_dermatologo, prenota_biopsia
from agenti.followup import (
    GIORNI_AVANZAMENTO_PER_SOLLECITO_ISTOLOGICO_DEMO,
    carica_esito_istologico,
    ottieni_casi_in_attesa_di_esito_istologico,
    ottieni_controlli_periodici,
    ottieni_stato_biopsia,
    sollecita_esito_istologico,
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


def _porta_a_biopsia_prenotata(nome_paziente: str, chiave_immagine: str) -> dict:
    """Porta un caso fino alla biopsia prenotata, passando per ACCOGLIENZA,
    GUIDA ALLA FOTO, ANALISI e INSTRADAMENTO, come farebbe l'app."""
    percorsi = genera_immagini_demo()
    caso_id = valuta_questionario(_id_paziente(nome_paziente))["caso_id"]
    valuta_foto(caso_id, percorsi[chiave_immagine].read_bytes())
    esito_analisi = analizza_caso(caso_id)
    assert esito_analisi["destinato_dermatologo"] is True
    instrada_caso(caso_id)
    esito_biopsia = prenota_biopsia(caso_id)
    return {"caso_id": caso_id, "paziente_id": _id_paziente(nome_paziente), **esito_biopsia}


def test_marta_biopsia_esito_maligno_e_concordanza():
    """Marta: il classificatore dice 'sospetta' (marta_nitida); un esito
    istologico maligno è quindi una CONCORDANZA (il sistema ha funzionato),
    non un caso da mettere in dubbio."""
    dati = _porta_a_biopsia_prenotata("Marta", "marta_nitida")

    esito = carica_esito_istologico(dati["caso_id"], "melanoma_in_situ")

    assert esito["categoria_confronto"] == CATEGORIA_CONCORDANZA

    connessione = ottieni_connessione()
    try:
        stato_caso = connessione.execute("SELECT stato FROM casi WHERE id = ?", (dati["caso_id"],)).fetchone()[0]
    finally:
        connessione.close()
    assert stato_caso == "chiuso_con_esito"

    # Esito maligno -> controllo ravvicinato (GIORNI_CONTROLLO_BREVE), a
    # partire da oggi (carica_esito_istologico non fa avanzare la data
    # simulata: solo sollecita_esito_istologico lo fa).
    data_controllo_attesa = (ottieni_data_simulata() + timedelta(days=GIORNI_CONTROLLO_BREVE)).isoformat()
    controlli = ottieni_controlli_periodici(dati["paziente_id"])
    assert len(controlli) == 1
    assert controlli[0]["data_prevista"] == data_controllo_attesa


def test_giulia_recuperata_da_regola_di_sicurezza_non_falso_negativo():
    """Il test più importante: Giulia ha un'analisi rassicurante
    (giulia_nitida -> 'probabilmente_benigna') ma ha dichiarato un neo
    cambiato: il caso è comunque andato al dermatologo per quella regola di
    sicurezza. Un esito istologico maligno deve essere contato come
    'recuperato da una regola di sicurezza', MAI come falso negativo."""
    dati = _porta_a_biopsia_prenotata("Giulia", "giulia_nitida")

    esito = carica_esito_istologico(dati["caso_id"], "melanoma_invasivo")

    assert esito["categoria_confronto"] == CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA


def test_caso_con_biopsia_esce_dalla_coda_ordinaria():
    dati = _porta_a_biopsia_prenotata("Paolo", "paolo_nitida")

    assert dati["caso_id"] not in [caso["caso_id"] for caso in ottieni_coda_dermatologo()]
    assert dati["caso_id"] in [caso["caso_id"] for caso in ottieni_casi_in_attesa_di_esito_istologico()]

    carica_esito_istologico(dati["caso_id"], "benigno")

    assert dati["caso_id"] not in [caso["caso_id"] for caso in ottieni_casi_in_attesa_di_esito_istologico()]
    assert dati["caso_id"] not in [caso["caso_id"] for caso in ottieni_coda_dermatologo()]


def test_prenota_biopsia_e_idempotente():
    dati = _porta_a_biopsia_prenotata("Paolo", "paolo_nitida")

    secondo_esito = prenota_biopsia(dati["caso_id"])

    assert secondo_esito["gia_prenotata"] is True
    assert secondo_esito["appuntamento_id"] == dati["appuntamento_id"]


def test_sollecito_esito_istologico_mancante():
    dati = _porta_a_biopsia_prenotata("Paolo", "paolo_nitida")

    primo = sollecita_esito_istologico(dati["appuntamento_id"])
    assert primo["azione"] == "sollecito_inviato"
    assert primo["numero_solleciti"] == 1

    secondo = sollecita_esito_istologico(dati["appuntamento_id"])
    assert secondo["numero_solleciti"] == 2

    casi_in_attesa = {caso["caso_id"]: caso for caso in ottieni_casi_in_attesa_di_esito_istologico()}
    assert casi_in_attesa[dati["caso_id"]]["numero_solleciti"] == 2


def test_sollecito_non_fa_nulla_se_lesito_e_gia_arrivato():
    dati = _porta_a_biopsia_prenotata("Paolo", "paolo_nitida")
    carica_esito_istologico(dati["caso_id"], "benigno")

    esito = sollecita_esito_istologico(dati["appuntamento_id"])

    assert esito["azione"] == "nessuna"


def test_stato_biopsia_per_il_paziente_non_rivela_mai_la_classificazione():
    dati = _porta_a_biopsia_prenotata("Paolo", "paolo_nitida")

    info_in_attesa = ottieni_stato_biopsia(dati["caso_id"])
    assert info_in_attesa["esito_disponibile"] is False

    carica_esito_istologico(dati["caso_id"], "melanoma_invasivo")

    info_disponibile = ottieni_stato_biopsia(dati["caso_id"])
    assert info_disponibile["esito_disponibile"] is True
    assert "classificazione" not in info_disponibile
    assert "melanoma" not in str(info_disponibile).lower()


if __name__ == "__main__":
    inizializza_database()

    test_marta_biopsia_esito_maligno_e_concordanza()
    print("OK - Marta: biopsia, esito maligno, confronto registrato come concordanza")

    test_giulia_recuperata_da_regola_di_sicurezza_non_falso_negativo()
    print("OK - Giulia: recuperata da una regola di sicurezza, non falso negativo")

    test_caso_con_biopsia_esce_dalla_coda_ordinaria()
    print("OK - un caso con biopsia richiesta esce dalla coda ed entra nell'elenco esiti in attesa")

    test_prenota_biopsia_e_idempotente()
    print("OK - prenota_biopsia non duplica l'appuntamento se richiamata due volte")

    test_sollecito_esito_istologico_mancante()
    print("OK - il sollecito per l'esito mancante avanza la data simulata e conta i solleciti")

    test_sollecito_non_fa_nulla_se_lesito_e_gia_arrivato()
    print("OK - nessun sollecito se l'esito è già arrivato")

    test_stato_biopsia_per_il_paziente_non_rivela_mai_la_classificazione()
    print("OK - lo stato mostrato al paziente non rivela mai la classificazione istologica")

    print("\nTEST SUPERATO")
