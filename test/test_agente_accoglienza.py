"""
Test dell'agente ACCOGLIENZA: verifica il triage sui 4 pazienti demo e la
resilienza quando il modello linguistico non è raggiungibile.

Questo file non fa MAI chiamate reali al modello linguistico (vedi CLAUDE.md,
sezione 11): il modello è disattivato subito qui sotto, prima di importare
qualunque modulo del progetto, così anche eseguendo il file direttamente
(non solo con pytest) non consuma quota. Per una vera chiamata a Gemini vedi
test/verifica_connessione_gemini.py (da lanciare a parte, su richiesta).
"""

import os

os.environ["DISATTIVA_MODELLO"] = "true"

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.database import inizializza_database, ottieni_connessione
from agenti.accoglienza import valuta_questionario


def _id_paziente(nome: str) -> int:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute("SELECT id FROM pazienti WHERE nome = ?", (nome,)).fetchone()
    finally:
        connessione.close()
    assert riga is not None, f"Paziente demo '{nome}' non trovato: hai inizializzato il database?"
    return riga[0]


def setup_module(module):
    inizializza_database()


def test_marta_rischio_alto_percorso_completo_dermatologo():
    esito = valuta_questionario(_id_paziente("Marta"))
    assert esito["priorita"] == "alta"
    assert esito["percorso"] == "foto"
    assert esito["destinato_dermatologo"] is True


def test_luca_rischio_basso_solo_prevenzione():
    esito = valuta_questionario(_id_paziente("Luca"))
    assert esito["priorita"] == "bassa"
    assert esito["percorso"] == "prevenzione"
    assert esito["destinato_dermatologo"] is False


def test_paolo_rischio_medio_percorso_con_foto():
    esito = valuta_questionario(_id_paziente("Paolo"))
    assert esito["priorita"] == "media"
    assert esito["percorso"] == "foto"
    assert esito["destinato_dermatologo"] is False


def test_giulia_rischio_basso_ma_neo_cambiato_va_al_dermatologo():
    esito = valuta_questionario(_id_paziente("Giulia"))
    assert esito["priorita"] == "bassa"
    assert esito["percorso"] == "foto"
    assert esito["destinato_dermatologo"] is True


def test_agente_funziona_anche_se_il_modello_non_e_raggiungibile():
    with patch("agenti.accoglienza.chiedi_al_modello", side_effect=RuntimeError("errore simulato per il test")):
        esito = valuta_questionario(_id_paziente("Marta"))

    assert esito["priorita"] == "alta"
    assert esito["percorso"] == "foto"
    assert esito["destinato_dermatologo"] is True
    assert esito["fonte_testo"] == "riserva"
    assert len(esito["testo_paziente"].strip()) > 0


def test_esito_viene_salvato_nel_database():
    esito = valuta_questionario(_id_paziente("Luca"))

    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT priorita, stato, testo_paziente, fonte_testo FROM casi WHERE id = ?",
            (esito["caso_id"],),
        ).fetchone()
    finally:
        connessione.close()

    assert riga is not None
    priorita, stato, testo_paziente, fonte_testo = riga
    assert priorita == "bassa"
    assert stato == "monitoraggio_domiciliare"
    assert testo_paziente is not None and len(testo_paziente.strip()) > 0
    assert fonte_testo in ("modello", "riserva")


if __name__ == "__main__":
    # Modello disattivato (vedi in cima al file): una sola valutazione per
    # paziente demo, con i testi di riserva. Le assert sotto riusano questi
    # stessi risultati invece di richiamare valuta_questionario() una seconda volta.
    inizializza_database()

    risultati_attesi = {
        "Marta": {"priorita": "alta", "percorso": "foto", "destinato_dermatologo": True},
        "Luca": {"priorita": "bassa", "percorso": "prevenzione", "destinato_dermatologo": False},
        "Paolo": {"priorita": "media", "percorso": "foto", "destinato_dermatologo": False},
        "Giulia": {"priorita": "bassa", "percorso": "foto", "destinato_dermatologo": True},
    }

    risultati = []
    for nome, atteso in risultati_attesi.items():
        esito = valuta_questionario(_id_paziente(nome))
        assert esito["priorita"] == atteso["priorita"], f"{nome}: priorità attesa {atteso['priorita']}, ottenuta {esito['priorita']}"
        assert esito["percorso"] == atteso["percorso"], f"{nome}: percorso atteso {atteso['percorso']}, ottenuto {esito['percorso']}"
        assert esito["destinato_dermatologo"] == atteso["destinato_dermatologo"], f"{nome}: destinazione dermatologo inattesa"
        risultati.append(esito)
        print(f"OK - {nome}: priorità {esito['priorita']}, percorso {esito['percorso']}")

    # Test di resilienza: nessuna chiamata reale, il modello è sostituito da un errore simulato.
    test_agente_funziona_anche_se_il_modello_non_e_raggiungibile()
    print("OK - agente resiliente: funziona anche se il modello linguistico fallisce")

    # Verifica che l'ultimo esito calcolato (Giulia) sia stato salvato correttamente.
    ultimo_caso_id = risultati[-1]["caso_id"]
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT priorita, stato, testo_paziente, fonte_testo FROM casi WHERE id = ?",
            (ultimo_caso_id,),
        ).fetchone()
    finally:
        connessione.close()
    assert riga is not None and riga[2] is not None and len(riga[2].strip()) > 0
    print("OK - esito salvato correttamente nel database")

    print("\n--- Tabella riassuntiva ---")
    print(f"{'Paziente':<10} {'Punteggio':<10} {'Priorità':<10} {'Percorso':<12} {'Motivo'}")
    for esito in risultati:
        print(f"{esito['nome_paziente']:<10} {esito['punteggio']:<10} {esito['priorita']:<10} {esito['percorso']:<12} {esito['motivo']}")

    print("\nTEST SUPERATO")
