"""
Test del modulo nucleo/qualita_immagine.py: verifica che le soglie (tarate sui
valori reali misurati sulle immagini demo) classifichino correttamente tutti e
4 i tipi di problema, oltre alle immagini nitide.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.dati_demo import genera_immagini_demo
from nucleo.qualita_immagine import valuta_qualita

_percorsi = genera_immagini_demo()


def _byte_immagine(chiave: str) -> bytes:
    return _percorsi[chiave].read_bytes()


def test_marta_nitida_accettata():
    esito = valuta_qualita(_byte_immagine("marta_nitida"))
    assert esito["utilizzabile"] is True
    assert esito["problema"] is None


def test_marta_sfocata_rifiutata_come_mossa():
    esito = valuta_qualita(_byte_immagine("marta_sfocata"))
    assert esito["utilizzabile"] is False
    assert esito["problema"] == "mossa"


def test_marta_troppo_scura_rifiutata():
    esito = valuta_qualita(_byte_immagine("marta_troppo_scura"))
    assert esito["utilizzabile"] is False
    assert esito["problema"] == "troppo_scura"


def test_marta_troppo_chiara_rifiutata():
    esito = valuta_qualita(_byte_immagine("marta_troppo_chiara"))
    assert esito["utilizzabile"] is False
    assert esito["problema"] == "troppo_chiara"


def test_marta_risoluzione_bassa_rifiutata():
    esito = valuta_qualita(_byte_immagine("marta_risoluzione_bassa"))
    assert esito["utilizzabile"] is False
    assert esito["problema"] == "risoluzione_bassa"


def test_giulia_e_paolo_nitide_accettate():
    for chiave in ["giulia_nitida", "paolo_nitida"]:
        esito = valuta_qualita(_byte_immagine(chiave))
        assert esito["utilizzabile"] is True, f"{chiave} doveva essere accettata"


if __name__ == "__main__":
    test_marta_nitida_accettata()
    print("OK - marta_nitida accettata")

    test_marta_sfocata_rifiutata_come_mossa()
    print("OK - marta_sfocata rifiutata come 'mossa'")

    test_marta_troppo_scura_rifiutata()
    print("OK - marta_troppo_scura rifiutata come 'troppo_scura'")

    test_marta_troppo_chiara_rifiutata()
    print("OK - marta_troppo_chiara rifiutata come 'troppo_chiara'")

    test_marta_risoluzione_bassa_rifiutata()
    print("OK - marta_risoluzione_bassa rifiutata come 'risoluzione_bassa'")

    test_giulia_e_paolo_nitide_accettate()
    print("OK - giulia_nitida e paolo_nitida accettate")

    print("\n--- Tabella valori misurati ---")
    print(f"{'Immagine':<26} {'Utilizzabile':<13} {'Problema':<18} {'Nitidezza':<11} {'Luminosità':<11} {'Risoluzione'}")
    for chiave, percorso in _percorsi.items():
        esito = valuta_qualita(percorso.read_bytes())
        print(
            f"{chiave:<26} {str(esito['utilizzabile']):<13} {str(esito['problema']):<18} "
            f"{esito['nitidezza']:<11.2f} {esito['luminosita']:<11.2f} {esito['larghezza']}x{esito['altezza']}"
        )

    print("\nTEST SUPERATO")
