"""
Test di nucleo/registro_audit.py: la funzione pura categorizza_confronto (i
sei rami possibili) e il conteggio aggregato sui dati demo.

Questo file non fa MAI chiamate reali al modello linguistico (vedi CLAUDE.md,
sezione 11): non serve nemmeno disattivarlo esplicitamente, dato che questo
modulo non lo tocca — ma lo facciamo comunque, per coerenza con tutta la
suite e perché inizializza_database() genera anche i 4 pazienti demo, che in
altri test passano dagli agenti che lo userebbero.
"""

import os

os.environ["DISATTIVA_MODELLO"] = "true"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.database import inizializza_database
from nucleo.registro_audit import (
    CATEGORIA_CONCORDANZA,
    CATEGORIA_FALSO_NEGATIVO,
    CATEGORIA_FALSO_POSITIVO,
    CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO,
    CATEGORIA_NON_CONCLUSIVI,
    CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA,
    calcola_riepilogo_audit,
    categorizza_confronto,
)


def test_sospetta_e_maligno_e_concordanza():
    categoria = categorizza_confronto(
        classificazione_algoritmo="sospetta",
        classificazione_istologica="melanoma_invasivo",
        gia_destinato_indipendentemente_dal_classificatore=False,
    )
    assert categoria == CATEGORIA_CONCORDANZA


def test_probabilmente_benigna_e_benigno_e_concordanza():
    categoria = categorizza_confronto(
        classificazione_algoritmo="probabilmente_benigna",
        classificazione_istologica="benigno",
        gia_destinato_indipendentemente_dal_classificatore=False,
    )
    assert categoria == CATEGORIA_CONCORDANZA


def test_sospetta_e_benigno_e_falso_positivo():
    categoria = categorizza_confronto(
        classificazione_algoritmo="sospetta",
        classificazione_istologica="benigno",
        gia_destinato_indipendentemente_dal_classificatore=False,
    )
    assert categoria == CATEGORIA_FALSO_POSITIVO


def test_rassicurante_e_maligno_senza_regola_di_sicurezza_e_falso_negativo():
    """Il test più importante: un esito rassicurante che si rivela maligno,
    SENZA che nessuna regola di sicurezza abbia già mandato il caso al
    dermatologo, va contato come falso negativo — mai mediato in una
    percentuale complessiva."""
    categoria = categorizza_confronto(
        classificazione_algoritmo="probabilmente_benigna",
        classificazione_istologica="melanoma_invasivo",
        gia_destinato_indipendentemente_dal_classificatore=False,
    )
    assert categoria == CATEGORIA_FALSO_NEGATIVO


def test_rassicurante_e_maligno_con_regola_di_sicurezza_e_recuperato():
    """Stesso esito rassicurante e stesso istologico maligno del test sopra,
    ma con una regola di sicurezza già attiva (neo cambiato o rischio alto):
    va contato nella categoria dedicata, mai come falso negativo."""
    categoria = categorizza_confronto(
        classificazione_algoritmo="probabilmente_benigna",
        classificazione_istologica="altra_lesione_maligna",
        gia_destinato_indipendentemente_dal_classificatore=True,
    )
    assert categoria == CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA


def test_non_conclusiva_e_non_conclusivi_indipendentemente_dallistologico():
    categoria_con_maligno = categorizza_confronto(
        classificazione_algoritmo="non_conclusiva",
        classificazione_istologica="melanoma_in_situ",
        gia_destinato_indipendentemente_dal_classificatore=False,
    )
    categoria_con_benigno = categorizza_confronto(
        classificazione_algoritmo="non_conclusiva",
        classificazione_istologica="benigno",
        gia_destinato_indipendentemente_dal_classificatore=True,
    )
    assert categoria_con_maligno == CATEGORIA_NON_CONCLUSIVI
    assert categoria_con_benigno == CATEGORIA_NON_CONCLUSIVI


def test_istologico_non_diagnostico_categoria_a_parte():
    categoria = categorizza_confronto(
        classificazione_algoritmo="sospetta",
        classificazione_istologica="non_diagnostico",
        gia_destinato_indipendentemente_dal_classificatore=False,
    )
    assert categoria == CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO


def test_riepilogo_audit_sui_dati_demo():
    """I ~30 casi storici fittizi (nucleo/dati_demo.py) devono produrre
    esattamente la distribuzione descritta in CLAUDE.md."""
    inizializza_database()

    riepilogo = calcola_riepilogo_audit()

    assert riepilogo["totale"] == 30
    conteggi = riepilogo["conteggi"]
    assert conteggi[CATEGORIA_CONCORDANZA] == 18
    assert conteggi[CATEGORIA_FALSO_POSITIVO] == 5
    assert conteggi[CATEGORIA_FALSO_NEGATIVO] == 2
    assert conteggi[CATEGORIA_NON_CONCLUSIVI] == 3
    assert conteggi[CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA] == 2
    assert conteggi[CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO] == 0
    # La somma dei conteggi separati deve sempre corrispondere al totale: mai
    # un caso perso o contato due volte.
    assert sum(conteggi.values()) == riepilogo["totale"]

    # Requisito esplicito (vedi CLAUDE.md): MAI una percentuale di accuratezza
    # unica. Se in futuro qualcuno la aggiungesse, questo test deve accorgersene.
    assert set(riepilogo.keys()) == {"conteggi", "totale"}


if __name__ == "__main__":
    test_sospetta_e_maligno_e_concordanza()
    print("OK - sospetta + maligno = concordanza")

    test_probabilmente_benigna_e_benigno_e_concordanza()
    print("OK - probabilmente benigna + benigno = concordanza")

    test_sospetta_e_benigno_e_falso_positivo()
    print("OK - sospetta + benigno = falso positivo")

    test_rassicurante_e_maligno_senza_regola_di_sicurezza_e_falso_negativo()
    print("OK - rassicurante + maligno, nessuna regola attiva = falso negativo")

    test_rassicurante_e_maligno_con_regola_di_sicurezza_e_recuperato()
    print("OK - rassicurante + maligno, regola di sicurezza attiva = recuperato (non falso negativo)")

    test_non_conclusiva_e_non_conclusivi_indipendentemente_dallistologico()
    print("OK - non conclusiva = non conclusivi, qualunque sia l'istologico")

    test_istologico_non_diagnostico_categoria_a_parte()
    print("OK - istologico non diagnostico è una categoria a parte")

    test_riepilogo_audit_sui_dati_demo()
    print("OK - il riepilogo sui dati demo corrisponde alla distribuzione attesa (30 casi)")

    print("\nTEST SUPERATO")
