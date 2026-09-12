"""
Test del modulo nucleo/classificatore.py: verifica gli esiti predefiniti per le
immagini demo, la stabilità rispetto al nome del file, e il confronto con lo
storico.
"""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.dati_demo import genera_immagini_demo
from nucleo.classificatore import analizza_lesione, confronta_con_precedente

_percorsi = genera_immagini_demo()


def test_marta_nitida_sospetta_confidenza_alta():
    esito = analizza_lesione(_percorsi["marta_nitida"].read_bytes())
    assert esito["classificazione"] == "sospetta"
    assert esito["confidenza"] >= 0.8


def test_giulia_probabilmente_benigna_confidenza_alta():
    esito = analizza_lesione(_percorsi["giulia_nitida"].read_bytes())
    assert esito["classificazione"] == "probabilmente_benigna"
    assert esito["confidenza"] >= 0.8


def test_paolo_non_conclusiva():
    esito = analizza_lesione(_percorsi["paolo_nitida"].read_bytes())
    assert esito["classificazione"] == "non_conclusiva"


def test_ogni_esito_include_avviso_di_simulazione():
    for chiave in ["marta_nitida", "giulia_nitida", "paolo_nitida"]:
        esito = analizza_lesione(_percorsi[chiave].read_bytes())
        assert "simulat" in esito["avviso_simulazione"].lower()


def test_stesso_file_rinominato_da_lo_stesso_esito():
    dati_originali = _percorsi["marta_nitida"].read_bytes()
    esito_originale = analizza_lesione(dati_originali)

    with tempfile.TemporaryDirectory() as cartella_temp:
        copia_rinominata = Path(cartella_temp) / "foto_completamente_diversa.jpg"
        shutil.copy(_percorsi["marta_nitida"], copia_rinominata)
        esito_copia = analizza_lesione(copia_rinominata.read_bytes())

    assert esito_copia["classificazione"] == esito_originale["classificazione"]
    assert esito_copia["confidenza"] == esito_originale["confidenza"]
    assert esito_copia["impronta_immagine"] == esito_originale["impronta_immagine"]


def test_immagine_sconosciuta_da_esito_deterministico_e_stabile():
    dati_finti = b"questa non e' una vera immagine, solo byte di prova"
    esito_1 = analizza_lesione(dati_finti)
    esito_2 = analizza_lesione(dati_finti)
    assert esito_1 == esito_2


def test_confronto_rileva_variazione_tra_marta_precedente_e_nitida():
    esito_precedente = analizza_lesione(_percorsi["marta_precedente"].read_bytes())
    esito_attuale = analizza_lesione(_percorsi["marta_nitida"].read_bytes())

    confronto = confronta_con_precedente(esito_attuale, esito_precedente)

    assert confronto["variazioni_rilevate"] is True
    assert "diametro" in confronto["descrizione"].lower()


if __name__ == "__main__":
    test_marta_nitida_sospetta_confidenza_alta()
    print("OK - Marta nitida: sospetta, confidenza alta")

    test_giulia_probabilmente_benigna_confidenza_alta()
    print("OK - Giulia: probabilmente benigna, confidenza alta")

    test_paolo_non_conclusiva()
    print("OK - Paolo: non conclusiva")

    test_ogni_esito_include_avviso_di_simulazione()
    print("OK - ogni esito include l'avviso di simulazione")

    test_stesso_file_rinominato_da_lo_stesso_esito()
    print("OK - stesso file rinominato dà lo stesso esito")

    test_immagine_sconosciuta_da_esito_deterministico_e_stabile()
    print("OK - immagine sconosciuta: esito deterministico e stabile")

    test_confronto_rileva_variazione_tra_marta_precedente_e_nitida()
    print("OK - confronto rileva la variazione tra Marta precedente e attuale")

    print("\nTEST SUPERATO")
