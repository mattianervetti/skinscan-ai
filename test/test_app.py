"""
Test dell'app Streamlit: verifica che si avvii senza errori e che il database
venga inizializzato correttamente all'avvio.
"""

import sys
from pathlib import Path

# Permette di importare i moduli del progetto anche se il test viene lanciato
# da un'altra cartella.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest

from nucleo.database import ottieni_connessione

_PERCORSO_APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_si_avvia_senza_errori():
    app = AppTest.from_file(_PERCORSO_APP)
    app.run(timeout=30)
    assert not app.exception, f"L'app ha sollevato un'eccezione: {app.exception}"


def test_database_inizializzato_dopo_avvio_app():
    app = AppTest.from_file(_PERCORSO_APP)
    app.run(timeout=30)

    connessione = ottieni_connessione()
    try:
        numero_pazienti = connessione.execute("SELECT COUNT(*) FROM pazienti").fetchone()[0]
    finally:
        connessione.close()

    assert numero_pazienti == 4


if __name__ == "__main__":
    test_app_si_avvia_senza_errori()
    print("OK - app avviata senza errori")

    test_database_inizializzato_dopo_avvio_app()
    print("OK - database inizializzato correttamente")

    print("TEST SUPERATO")
