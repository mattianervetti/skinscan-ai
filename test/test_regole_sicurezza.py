"""
Test delle regole di triage in nucleo/regole_sicurezza.py: funzioni pure, nessun
database e nessun modello linguistico coinvolti.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.regole_sicurezza import (
    GIORNI_CONTROLLO_BREVE,
    GIORNI_CONTROLLO_LUNGO,
    GIORNI_CONTROLLO_MEDIO,
    calcola_punteggio_rischio_costituzionale,
    decidi_intervallo_controllo,
    decidi_percorso,
)


def _rischio(**kwargs) -> dict:
    valori = dict(
        eta=30,
        fototipo=3,
        categoria_nei="<20",
        familiarita_melanoma=False,
        melanoma_pregresso=False,
        immunosoppressione=False,
    )
    valori.update(kwargs)
    return calcola_punteggio_rischio_costituzionale(**valori)


def test_marta_rischio_alto():
    esito = _rischio(eta=34, fototipo=2, categoria_nei=">50", familiarita_melanoma=True)
    assert esito["punteggio"] == 5  # Marta non ha melanoma pregresso: punteggio invariato
    assert esito["priorita"] == "alta"


def test_luca_rischio_basso():
    esito = _rischio(eta=41, fototipo=4, categoria_nei="<20")
    assert esito["punteggio"] == 0
    assert esito["priorita"] == "bassa"


def test_paolo_rischio_medio():
    esito = _rischio(eta=58, fototipo=2, categoria_nei="20-50", familiarita_melanoma=True)
    assert esito["punteggio"] == 4
    assert esito["priorita"] == "media"


def test_giulia_rischio_basso():
    esito = _rischio(eta=29, fototipo=3, categoria_nei="20-50")
    assert esito["punteggio"] == 1
    assert esito["priorita"] == "bassa"


def test_solo_melanoma_pregresso_da_rischio_alto():
    esito = _rischio(melanoma_pregresso=True)
    assert esito["punteggio"] == 5
    assert esito["priorita"] == "alta"


def test_melanoma_pregresso_piu_un_altro_fattore_resta_alto():
    esito = _rischio(melanoma_pregresso=True, eta=65)
    assert esito["punteggio"] == 6
    assert esito["priorita"] == "alta"


def test_tutti_i_fattori_negativi_danno_rischio_basso():
    esito = _rischio(eta=25, fototipo=4, categoria_nei="<20")
    assert esito["punteggio"] == 0
    assert esito["priorita"] == "bassa"


def test_soglie_esatte():
    assert _rischio(fototipo=2)["priorita"] == "bassa"  # punteggio 1
    assert _rischio(fototipo=1)["priorita"] == "media"  # punteggio 2
    assert _rischio(familiarita_melanoma=True, fototipo=1)["priorita"] == "media"  # punteggio 4
    assert _rischio(melanoma_pregresso=True)["priorita"] == "alta"  # punteggio 5


def test_rischio_basso_con_neo_cambiato_non_e_mai_solo_prevenzione():
    esito_percorso = decidi_percorso("bassa", neo_cambiato=True)
    assert esito_percorso["percorso"] == "foto"
    assert esito_percorso["destinato_dermatologo"] is True


def test_rischio_basso_senza_sintomi_e_prevenzione():
    esito_percorso = decidi_percorso("bassa", neo_cambiato=False)
    assert esito_percorso["percorso"] == "prevenzione"
    assert esito_percorso["destinato_dermatologo"] is False


def test_rischio_medio_senza_sintomi_richiede_foto_ma_non_dermatologo():
    esito_percorso = decidi_percorso("media", neo_cambiato=False)
    assert esito_percorso["percorso"] == "foto"
    assert esito_percorso["destinato_dermatologo"] is False


def test_rischio_alto_senza_sintomi_va_comunque_al_dermatologo():
    esito_percorso = decidi_percorso("alta", neo_cambiato=False)
    assert esito_percorso["percorso"] == "foto"
    assert esito_percorso["destinato_dermatologo"] is True


def test_intervallo_controllo_esito_maligno_e_sempre_breve():
    # Anche con priorità bassa: un esito maligno già trovato vale più della priorità costituzionale.
    esito = decidi_intervallo_controllo(priorita="bassa", classificazione_istologica="melanoma_invasivo")
    assert esito["giorni"] == GIORNI_CONTROLLO_BREVE


def test_intervallo_controllo_priorita_alta_senza_esito_maligno_e_medio():
    esito = decidi_intervallo_controllo(priorita="alta", classificazione_istologica="benigno")
    assert esito["giorni"] == GIORNI_CONTROLLO_MEDIO


def test_intervallo_controllo_priorita_alta_senza_biopsia_e_medio():
    esito = decidi_intervallo_controllo(priorita="alta", classificazione_istologica=None)
    assert esito["giorni"] == GIORNI_CONTROLLO_MEDIO


def test_intervallo_controllo_priorita_bassa_o_media_senza_esito_maligno_e_lungo():
    assert decidi_intervallo_controllo(priorita="bassa", classificazione_istologica="benigno")["giorni"] == GIORNI_CONTROLLO_LUNGO
    assert decidi_intervallo_controllo(priorita="media", classificazione_istologica=None)["giorni"] == GIORNI_CONTROLLO_LUNGO


if __name__ == "__main__":
    test_marta_rischio_alto()
    test_luca_rischio_basso()
    test_paolo_rischio_medio()
    test_giulia_rischio_basso()
    test_solo_melanoma_pregresso_da_rischio_alto()
    test_melanoma_pregresso_piu_un_altro_fattore_resta_alto()
    test_tutti_i_fattori_negativi_danno_rischio_basso()
    test_soglie_esatte()
    test_rischio_basso_con_neo_cambiato_non_e_mai_solo_prevenzione()
    test_rischio_basso_senza_sintomi_e_prevenzione()
    test_rischio_medio_senza_sintomi_richiede_foto_ma_non_dermatologo()
    test_rischio_alto_senza_sintomi_va_comunque_al_dermatologo()
    test_intervallo_controllo_esito_maligno_e_sempre_breve()
    test_intervallo_controllo_priorita_alta_senza_esito_maligno_e_medio()
    test_intervallo_controllo_priorita_alta_senza_biopsia_e_medio()
    test_intervallo_controllo_priorita_bassa_o_media_senza_esito_maligno_e_lungo()
    print("TEST SUPERATO")
