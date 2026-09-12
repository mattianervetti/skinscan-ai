"""
Test dell'agente GUIDA ALLA FOTO: verifica la regola di non esclusione dopo 3
tentativi falliti, la resilienza senza modello linguistico, e la registrazione
di ogni tentativo nel registro.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.database import inizializza_database, ottieni_connessione
from nucleo.dati_demo import genera_immagini_demo
from agenti.accoglienza import valuta_questionario
from agenti.guida_foto import TENTATIVI_MASSIMI, valuta_foto

_VALORE_ORIGINALE_DISATTIVA_MODELLO = None


def setup_module(module):
    # I test verificano misure/decisioni (deterministiche), non il testo
    # generato da Gemini: eseguiti col modello disattivato, zero consumo quota.
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


def _apri_nuovo_caso_marta() -> int:
    """Marta ha sempre percorso 'foto' (neo cambiato): ogni chiamata apre un
    nuovo caso pulito, utile per isolare i test tra loro."""
    esito = valuta_questionario(_id_paziente("Marta"))
    return esito["caso_id"]


def _conta_righe_log(caso_id: int) -> int:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT COUNT(*) FROM log_agenti WHERE caso_id = ? AND agente = 'GUIDA ALLA FOTO'", (caso_id,)
        ).fetchone()
    finally:
        connessione.close()
    return riga[0]


def test_foto_nitida_accettata():
    percorsi = genera_immagini_demo()
    caso_id = _apri_nuovo_caso_marta()

    risultato = valuta_foto(caso_id, percorsi["marta_nitida"].read_bytes())

    assert risultato["accettata"] is True
    assert risultato["qualita_insufficiente_forzata"] is False
    assert risultato["problema"] is None
    assert _conta_righe_log(caso_id) == 1


def test_foto_sfocata_rifiutata_con_problema_mossa():
    percorsi = genera_immagini_demo()
    caso_id = _apri_nuovo_caso_marta()

    risultato = valuta_foto(caso_id, percorsi["marta_sfocata"].read_bytes())

    assert risultato["accettata"] is False
    assert risultato["problema"] == "mossa"
    assert len(risultato["testo_paziente"].strip()) > 0


def test_dopo_tre_rifiuti_il_caso_e_accettato_e_mai_bloccato():
    percorsi = genera_immagini_demo()
    caso_id = _apri_nuovo_caso_marta()
    dati_sfocati = percorsi["marta_sfocata"].read_bytes()

    risultato_1 = valuta_foto(caso_id, dati_sfocati)
    assert risultato_1["accettata"] is False
    assert risultato_1["qualita_insufficiente_forzata"] is False

    risultato_2 = valuta_foto(caso_id, dati_sfocati)
    assert risultato_2["accettata"] is False
    assert risultato_2["qualita_insufficiente_forzata"] is False

    risultato_3 = valuta_foto(caso_id, dati_sfocati)
    assert risultato_3["tentativo_numero"] == TENTATIVI_MASSIMI
    assert risultato_3["accettata"] is True  # MAI bloccato: accettata comunque
    assert risultato_3["qualita_insufficiente_forzata"] is True

    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT stato, qualita_foto_insufficiente FROM casi WHERE id = ?", (caso_id,)
        ).fetchone()
    finally:
        connessione.close()
    assert riga[0] == "in_coda_dermatologo"
    assert riga[1] == 1

    assert _conta_righe_log(caso_id) == 3


def test_funziona_anche_se_il_modello_non_e_raggiungibile():
    percorsi = genera_immagini_demo()
    caso_id = _apri_nuovo_caso_marta()

    with patch("agenti.guida_foto.chiedi_al_modello", side_effect=RuntimeError("errore simulato per il test")):
        risultato = valuta_foto(caso_id, percorsi["marta_sfocata"].read_bytes())

    assert risultato["accettata"] is False
    assert risultato["fonte_testo"] == "riserva"
    assert len(risultato["testo_paziente"].strip()) > 0


def test_ogni_tentativo_viene_registrato_nel_log_con_i_valori_misurati():
    percorsi = genera_immagini_demo()
    caso_id = _apri_nuovo_caso_marta()

    valuta_foto(caso_id, percorsi["marta_sfocata"].read_bytes())
    valuta_foto(caso_id, percorsi["marta_nitida"].read_bytes())

    connessione = ottieni_connessione()
    try:
        righe = connessione.execute(
            "SELECT input, decisione, motivo FROM log_agenti WHERE caso_id = ? AND agente = 'GUIDA ALLA FOTO' ORDER BY id",
            (caso_id,),
        ).fetchall()
    finally:
        connessione.close()

    assert len(righe) == 2
    assert "nitidezza" in righe[0][0].lower()
    assert "rifiutata" in righe[0][1].lower()
    assert "accettata" in righe[1][1].lower()


if __name__ == "__main__":
    inizializza_database()

    test_foto_nitida_accettata()
    print("OK - foto nitida accettata")

    test_foto_sfocata_rifiutata_con_problema_mossa()
    print("OK - foto sfocata rifiutata con problema 'mossa'")

    test_dopo_tre_rifiuti_il_caso_e_accettato_e_mai_bloccato()
    print("OK - dopo 3 rifiuti il caso è accettato comunque, mai bloccato")

    test_funziona_anche_se_il_modello_non_e_raggiungibile()
    print("OK - agente resiliente: funziona anche se il modello linguistico fallisce")

    test_ogni_tentativo_viene_registrato_nel_log_con_i_valori_misurati()
    print("OK - ogni tentativo registrato nel log con i valori misurati")

    print("\nTEST SUPERATO")
