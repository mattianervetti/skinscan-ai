"""
Test di nucleo/tempo_simulato.py: la data simulata usata solo dall'agente
INSTRADAMENTO. Verifica inizializzazione alla data reale, avanzamento e
reset (sia inizializza_database sia resetta_database la riportano a oggi).
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.database import inizializza_database, resetta_database
from nucleo.tempo_simulato import avanza_data_simulata, ottieni_data_simulata, ottieni_istante_simulato


def test_data_simulata_inizializzata_alla_data_reale():
    inizializza_database()
    assert ottieni_data_simulata() == date.today()


def test_avanza_data_simulata_di_n_giorni():
    resetta_database()
    partenza = ottieni_data_simulata()

    nuova = avanza_data_simulata(2)

    assert nuova == partenza + timedelta(days=2)
    assert ottieni_data_simulata() == partenza + timedelta(days=2)

    nuova2 = avanza_data_simulata(3)
    assert nuova2 == partenza + timedelta(days=5)


def test_istante_simulato_usa_la_data_simulata():
    resetta_database()
    avanza_data_simulata(4)

    istante = ottieni_istante_simulato()

    assert istante.date() == ottieni_data_simulata()


def test_resetta_database_riporta_la_data_simulata_a_oggi():
    avanza_data_simulata(10)
    assert ottieni_data_simulata() != date.today()

    resetta_database()

    assert ottieni_data_simulata() == date.today()


if __name__ == "__main__":
    test_data_simulata_inizializzata_alla_data_reale()
    print("OK - data simulata inizializzata alla data reale")

    test_avanza_data_simulata_di_n_giorni()
    print("OK - la data simulata avanza del numero di giorni richiesto")

    test_istante_simulato_usa_la_data_simulata()
    print("OK - l'istante simulato usa la data simulata (con l'ora reale)")

    test_resetta_database_riporta_la_data_simulata_a_oggi()
    print("OK - resetta_database riporta la data simulata a oggi")

    print("\nTEST SUPERATO")
