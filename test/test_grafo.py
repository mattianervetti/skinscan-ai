"""
Test del grafo LangGraph (agenti/grafo.py, Fase 3 passo 1): verifica che il
percorso seguito dal grafo per ciascuno dei 4 pazienti demo corrisponda a
quello prodotto dagli stessi agenti chiamati direttamente, come fa oggi
l'interfaccia. Se i due risultati divergono, il grafo è sbagliato, non il
sistema esistente (che resta la fonte di verità: è testato da solo in
test_agente_*.py).

Il grafo NON è collegato a pages/*.py o app.py in questo passo: qui lo si
esegue e verifica isolatamente.

Questo file non fa MAI chiamate reali al modello linguistico (vedi CLAUDE.md,
sezione 11): il modello è disattivato subito qui sotto, prima di importare
qualunque modulo del progetto.
"""

import os

os.environ["DISATTIVA_MODELLO"] = "true"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.graph import END

from nucleo.database import inizializza_database, ottieni_connessione
from nucleo.dati_demo import genera_immagini_demo
from agenti.accoglienza import valuta_questionario
from agenti.guida_foto import valuta_foto
from agenti.analisi import analizza_caso
from agenti.instradamento import instrada_caso, prenota_biopsia
from agenti.grafo import _dopo_instradamento, costruisci_grafo, nodo_followup


def setup_module(module):
    inizializza_database()


def _id_paziente(nome: str) -> int:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute("SELECT id FROM pazienti WHERE nome = ?", (nome,)).fetchone()
    finally:
        connessione.close()
    return riga[0]


def _leggi_caso(caso_id: int) -> dict:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute("SELECT priorita, stato FROM casi WHERE id = ?", (caso_id,)).fetchone()
    finally:
        connessione.close()
    priorita, stato = riga
    return {"priorita": priorita, "stato": stato}


def _stato_iniziale(paziente_id: int, foto_da_provare: list[bytes] | None = None) -> dict:
    return {
        "paziente_id": paziente_id,
        "caso_id": None,
        "percorso": None,
        "destinato_dermatologo": False,
        "foto_da_provare": foto_da_provare or [],
        "foto_accettata": False,
        "foto_qualita_insufficiente_forzata": False,
        "esito_istologico_da_caricare": None,
        "percorso_nodi": [],
    }


def test_luca_il_grafo_termina_dopo_accoglienza_senza_foto():
    grafo = costruisci_grafo()

    esito_diretto = valuta_questionario(_id_paziente("Luca"))
    esito_grafo = grafo.invoke(_stato_iniziale(_id_paziente("Luca")))

    assert esito_grafo["percorso_nodi"] == ["ACCOGLIENZA"]
    assert esito_grafo["percorso"] == "prevenzione"
    assert esito_grafo["destinato_dermatologo"] is False

    # Stesso risultato del percorso "attuale" (chiamata diretta all'agente).
    assert esito_grafo["percorso"] == esito_diretto["percorso"]
    assert esito_grafo["destinato_dermatologo"] == esito_diretto["destinato_dermatologo"]
    caso_diretto = _leggi_caso(esito_diretto["caso_id"])
    caso_grafo = _leggi_caso(esito_grafo["caso_id"])
    assert caso_grafo["priorita"] == caso_diretto["priorita"]


def test_giulia_percorso_completo_fino_allinstradamento():
    grafo = costruisci_grafo()
    percorsi = genera_immagini_demo()
    foto = percorsi["giulia_nitida"].read_bytes()

    # Percorso "attuale": stessa sequenza di chiamate dirette usata dagli altri test.
    caso_diretto = valuta_questionario(_id_paziente("Giulia"))["caso_id"]
    valuta_foto(caso_diretto, foto)
    esito_analisi_diretto = analizza_caso(caso_diretto)

    esito_grafo = grafo.invoke(_stato_iniziale(_id_paziente("Giulia"), foto_da_provare=[foto]))

    assert esito_grafo["percorso_nodi"] == ["ACCOGLIENZA", "GUIDA ALLA FOTO", "ANALISI", "INSTRADAMENTO"]
    assert esito_grafo["destinato_dermatologo"] is True
    assert esito_grafo["destinato_dermatologo"] == esito_analisi_diretto["destinato_dermatologo"]

    caso_grafo = _leggi_caso(esito_grafo["caso_id"])
    assert caso_grafo["stato"] == "in_coda_dermatologo"


def test_marta_il_grafo_ripete_la_foto_rifiutata():
    grafo = costruisci_grafo()
    percorsi = genera_immagini_demo()
    foto_sfocata = percorsi["marta_sfocata"].read_bytes()
    foto_nitida = percorsi["marta_nitida"].read_bytes()

    caso_diretto = valuta_questionario(_id_paziente("Marta"))["caso_id"]
    risultato_sfocata = valuta_foto(caso_diretto, foto_sfocata)
    assert risultato_sfocata["accettata"] is False  # verifica la premessa del test
    valuta_foto(caso_diretto, foto_nitida)
    esito_analisi_diretto = analizza_caso(caso_diretto)

    esito_grafo = grafo.invoke(
        _stato_iniziale(_id_paziente("Marta"), foto_da_provare=[foto_sfocata, foto_nitida])
    )

    assert esito_grafo["percorso_nodi"] == [
        "ACCOGLIENZA",
        "GUIDA ALLA FOTO",
        "GUIDA ALLA FOTO",
        "ANALISI",
        "INSTRADAMENTO",
    ]
    assert esito_grafo["destinato_dermatologo"] is True
    assert esito_grafo["destinato_dermatologo"] == esito_analisi_diretto["destinato_dermatologo"]


def test_paolo_analisi_lo_destina_al_dermatologo_anche_se_accoglienza_no():
    """Caso interessante: l'accoglienza da sola NON destina Paolo al
    dermatologo (rischio medio, nessun sintomo); è l'agente ANALISI (esito
    'non conclusiva') a farlo scattare. Verifica che lo stato del grafo si
    aggiorni correttamente da un nodo all'altro, non solo al primo."""
    grafo = costruisci_grafo()
    percorsi = genera_immagini_demo()
    foto = percorsi["paolo_nitida"].read_bytes()

    caso_diretto = valuta_questionario(_id_paziente("Paolo"))
    assert caso_diretto["destinato_dermatologo"] is False  # premessa: l'accoglienza da sola non lo destina
    valuta_foto(caso_diretto["caso_id"], foto)
    esito_analisi_diretto = analizza_caso(caso_diretto["caso_id"])
    assert esito_analisi_diretto["destinato_dermatologo"] is True  # l'analisi sì

    esito_grafo = grafo.invoke(_stato_iniziale(_id_paziente("Paolo"), foto_da_provare=[foto]))

    assert esito_grafo["percorso_nodi"] == ["ACCOGLIENZA", "GUIDA ALLA FOTO", "ANALISI", "INSTRADAMENTO"]
    assert esito_grafo["destinato_dermatologo"] is True


def test_dopo_instradamento_va_a_followup_solo_se_atteso_un_esito():
    assert _dopo_instradamento({"esito_istologico_da_caricare": None}) == END
    assert _dopo_instradamento({"esito_istologico_da_caricare": "benigno"}) == "followup"


def test_nodo_followup_registra_lesito():
    """Nessuno dei 4 casi demo richiesti raggiunge FOLLOW-UP nel grafo (la
    richiesta di biopsia è una decisione del dermatologo, fuori dal grafo):
    un nodo mai eseguito è un nodo che non sappiamo se funziona, quindi lo
    testiamo qui direttamente, dopo aver simulato la biopsia già richiesta
    come farebbe il dermatologo dall'interfaccia."""
    percorsi = genera_immagini_demo()
    caso_id = valuta_questionario(_id_paziente("Giulia"))["caso_id"]
    valuta_foto(caso_id, percorsi["giulia_nitida"].read_bytes())
    analizza_caso(caso_id)
    instrada_caso(caso_id)
    prenota_biopsia(caso_id)  # decisione del dermatologo, fuori dal grafo

    stato = _stato_iniziale(_id_paziente("Giulia"))
    stato["caso_id"] = caso_id
    stato["esito_istologico_da_caricare"] = "melanoma_invasivo"

    esito_nodo = nodo_followup(stato)

    assert esito_nodo["percorso_nodi"] == ["FOLLOW-UP"]
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT categoria_confronto FROM esiti_istologici WHERE caso_id = ?", (caso_id,)
        ).fetchone()
    finally:
        connessione.close()
    assert riga is not None  # l'esito è stato davvero registrato dal nodo


if __name__ == "__main__":
    inizializza_database()

    test_luca_il_grafo_termina_dopo_accoglienza_senza_foto()
    print("OK - Luca: il grafo termina dopo l'accoglienza, senza foto")

    test_giulia_percorso_completo_fino_allinstradamento()
    print("OK - Giulia: percorso completo fino all'instradamento")

    test_marta_il_grafo_ripete_la_foto_rifiutata()
    print("OK - Marta: la guida alla foto si ripete (sfocata poi nitida)")

    test_paolo_analisi_lo_destina_al_dermatologo_anche_se_accoglienza_no()
    print("OK - Paolo: l'analisi lo destina al dermatologo anche se l'accoglienza da sola no")

    test_dopo_instradamento_va_a_followup_solo_se_atteso_un_esito()
    print("OK - dopo instradamento si va a follow-up solo se atteso un esito istologico")

    test_nodo_followup_registra_lesito()
    print("OK - il nodo FOLLOW-UP registra correttamente l'esito")

    print("\nTEST SUPERATO")
