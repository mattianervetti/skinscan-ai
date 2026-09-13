"""
Test del database: verifica che si crei da zero, che contenga i 4 pazienti demo
con i dati corretti, che il reset funzioni, e che le immagini demo esistano e
siano leggibili.
"""

import sys
from pathlib import Path

# Permette di importare "nucleo" anche se il test viene lanciato da un'altra cartella.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from nucleo.database import PERCORSO_DATABASE, inizializza_database, ottieni_connessione, resetta_database
from nucleo.dati_demo import genera_immagini_demo


_NOMI_PAZIENTI_DEMO = ("Marta", "Luca", "Paolo", "Giulia")


def _pazienti_come_dizionario(connessione):
    # Solo i 4 pazienti demo con cui si interagisce: il database contiene anche
    # ~30 casi storici fittizi per il registro di audit (nucleo/dati_demo.py),
    # che non sono "pazienti demo" in questo senso.
    segnaposto = ",".join("?" * len(_NOMI_PAZIENTI_DEMO))
    cursore = connessione.execute(
        f"SELECT nome, eta, fototipo FROM pazienti WHERE nome IN ({segnaposto}) ORDER BY nome",
        _NOMI_PAZIENTI_DEMO,
    )
    return {nome: {"eta": eta, "fototipo": fototipo} for nome, eta, fototipo in cursore.fetchall()}


def test_database_si_crea_da_zero_con_i_quattro_pazienti():
    if PERCORSO_DATABASE.exists():
        PERCORSO_DATABASE.unlink()

    inizializza_database()

    connessione = ottieni_connessione()
    try:
        pazienti = _pazienti_come_dizionario(connessione)
    finally:
        connessione.close()

    assert set(pazienti.keys()) == set(_NOMI_PAZIENTI_DEMO)
    assert pazienti["Marta"]["eta"] == 34
    assert pazienti["Luca"]["fototipo"] == 4


def test_questionari_coerenti_con_il_rischio_atteso():
    inizializza_database()

    connessione = ottieni_connessione()
    try:
        righe = connessione.execute(
            """SELECT p.nome, q.neo_cambiato, q.familiarita_melanoma, q.categoria_nei
               FROM questionari q JOIN pazienti p ON p.id = q.paziente_id"""
        ).fetchall()
    finally:
        connessione.close()

    dati = {nome: (neo_cambiato, familiarita, categoria) for nome, neo_cambiato, familiarita, categoria in righe}

    assert dati["Marta"] == (1, 1, ">50")
    assert dati["Luca"] == (0, 0, "<20")
    assert dati["Paolo"] == (0, 1, "20-50")
    assert dati["Giulia"] == (1, 0, "20-50")


def test_reset_riporta_alla_situazione_di_partenza():
    inizializza_database()

    connessione = ottieni_connessione()
    try:
        connessione.execute("UPDATE pazienti SET eta = 99 WHERE nome = 'Marta'")
        connessione.commit()
    finally:
        connessione.close()

    resetta_database()

    connessione = ottieni_connessione()
    try:
        eta_marta = connessione.execute("SELECT eta FROM pazienti WHERE nome = 'Marta'").fetchone()[0]
        # Conta solo i 4 pazienti demo con cui si interagisce: il totale include
        # anche i ~30 casi storici fittizi generati per il registro di audit
        # (nucleo/dati_demo.py), che non sono "pazienti demo" in questo senso.
        numero_pazienti_demo = connessione.execute(
            "SELECT COUNT(*) FROM pazienti WHERE nome IN ('Marta', 'Luca', 'Paolo', 'Giulia')"
        ).fetchone()[0]
    finally:
        connessione.close()

    assert eta_marta == 34
    assert numero_pazienti_demo == 4


def test_immagini_demo_esistono_e_sono_leggibili():
    percorsi = genera_immagini_demo()
    assert len(percorsi) == 8  # 5 originali + 3 varianti (scura/chiara/bassa risoluzione) per l'agente GUIDA ALLA FOTO
    for percorso in percorsi.values():
        assert percorso.exists(), f"Immagine mancante: {percorso}"
        with Image.open(percorso) as immagine:
            immagine.verify()


if __name__ == "__main__":
    test_database_si_crea_da_zero_con_i_quattro_pazienti()
    print("OK - database creato da zero con i 4 pazienti")

    test_questionari_coerenti_con_il_rischio_atteso()
    print("OK - dati dei questionari coerenti")

    test_reset_riporta_alla_situazione_di_partenza()
    print("OK - reset funzionante")

    test_immagini_demo_esistono_e_sono_leggibili()
    print("OK - immagini demo presenti e leggibili")

    print("TEST SUPERATO")
