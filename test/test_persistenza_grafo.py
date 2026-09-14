"""
Test della persistenza dello stato del grafo LangGraph (agenti/grafo.py, Fase 3
passo 2): verifica che il checkpointer (SqliteSaver, file data/stato_grafo.db)
salvi davvero il punto in cui il grafo si è fermato, che la ripresa non
riesegua i nodi già completati, che due casi diversi non si mescolino, che lo
stato sopravviva alla chiusura e riapertura del processo Python, e che il
reset della demo cancelli anche questo stato (altrimenti, dopo un reset, un
paziente demo riprenderebbe il percorso a metà della sessione precedente
invece di ripartire da capo — un problema concreto per una demo dal vivo
rifatta più volte, segnalato esplicitamente da Mattia).

NON usa ancora il meccanismo di interruzione per l'approvazione del
dermatologo (arriva al passo 3.3): per fermare il grafo a metà in modo
controllato usa interrupt_before, una funzionalità già pronta di LangGraph,
solo per questi test.

Questo file non fa MAI chiamate reali al modello linguistico (vedi CLAUDE.md,
sezione 11): il modello è disattivato subito qui sotto, prima di importare
qualunque modulo del progetto.
"""

import os

os.environ["DISATTIVA_MODELLO"] = "true"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.checkpoint.sqlite import SqliteSaver

from nucleo.database import inizializza_database, ottieni_connessione, resetta_database
from nucleo.dati_demo import genera_immagini_demo
from agenti.grafo import (
    cancella_stato_grafo,
    costruisci_grafo,
    ottieni_connessione_stato_grafo,
    thread_id_per_paziente,
)


def setup_module(module):
    inizializza_database()
    # Stato pulito a ogni esecuzione della suite: senza questo, un file
    # data/stato_grafo.db lasciato da un lancio precedente della suite
    # falserebbe le verifiche di questo file (che controllano esattamente
    # cosa contiene quel file, non solo che "contenga qualcosa").
    cancella_stato_grafo()


def _id_paziente(nome: str) -> int:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute("SELECT id FROM pazienti WHERE nome = ?", (nome,)).fetchone()
    finally:
        connessione.close()
    return riga[0]


def _conta_azioni(caso_id: int, agente: str) -> int:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            "SELECT COUNT(*) FROM log_agenti WHERE caso_id = ? AND agente = ?", (caso_id, agente)
        ).fetchone()
    finally:
        connessione.close()
    return riga[0]


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


def test_fermo_a_meta_percorso_lo_stato_salvato_indica_il_punto_esatto():
    """Ferma il grafo PRIMA del nodo ANALISI (Giulia) e verifica che lo stato
    salvato rifletta esattamente quel punto: solo i due nodi precedenti
    eseguiti, e get_state().next indica il nodo successivo corretto."""
    percorsi = genera_immagini_demo()
    foto = percorsi["giulia_nitida"].read_bytes()
    paziente_id = _id_paziente("Giulia")
    config = {"configurable": {"thread_id": thread_id_per_paziente(paziente_id)}}

    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo = costruisci_grafo(checkpointer=SqliteSaver(connessione), interrupt_before=["analisi"])
        esito = grafo.invoke(_stato_iniziale(paziente_id, foto_da_provare=[foto]), config)

        assert esito["percorso_nodi"] == ["ACCOGLIENZA", "GUIDA ALLA FOTO"]

        stato_salvato = grafo.get_state(config)
        assert stato_salvato.next == ("analisi",)
        assert stato_salvato.values["percorso_nodi"] == ["ACCOGLIENZA", "GUIDA ALLA FOTO"]
        assert stato_salvato.values["foto_accettata"] is True
        assert stato_salvato.values["caso_id"] == esito["caso_id"]
    finally:
        connessione.close()


def test_riprende_lesecuzione_senza_rieseguire_i_nodi_gia_completati():
    """Ferma il grafo prima di ANALISI (Paolo), poi lo riprende con un grafo
    compilato SENZA interrupt_before: deve proseguire fino alla fine senza
    rieseguire ACCOGLIENZA e GUIDA ALLA FOTO (verificato contando le azioni già
    registrate nel log, non solo il percorso_nodi restituito)."""
    percorsi = genera_immagini_demo()
    foto = percorsi["paolo_nitida"].read_bytes()
    paziente_id = _id_paziente("Paolo")
    config = {"configurable": {"thread_id": thread_id_per_paziente(paziente_id)}}

    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo_con_pausa = costruisci_grafo(checkpointer=SqliteSaver(connessione), interrupt_before=["analisi"])
        esito_pausa = grafo_con_pausa.invoke(_stato_iniziale(paziente_id, foto_da_provare=[foto]), config)
        caso_id = esito_pausa["caso_id"]

        azioni_accoglienza_prima = _conta_azioni(caso_id, "ACCOGLIENZA")
        azioni_foto_prima = _conta_azioni(caso_id, "GUIDA ALLA FOTO")
        assert azioni_accoglienza_prima == 1
        assert azioni_foto_prima == 1  # premessa: un solo tentativo, foto nitida al primo colpo

        # Ripresa: stesso thread_id, nessun input nuovo (None), grafo SENZA
        # interrupt_before, quindi prosegue fino a INSTRADAMENTO compreso.
        grafo_senza_pausa = costruisci_grafo(checkpointer=SqliteSaver(connessione))
        esito_finale = grafo_senza_pausa.invoke(None, config)

        assert esito_finale["percorso_nodi"] == [
            "ACCOGLIENZA", "GUIDA ALLA FOTO", "ANALISI", "INSTRADAMENTO",
        ]
        assert esito_finale["destinato_dermatologo"] is True

        # I nodi già completati prima della pausa non sono stati rieseguiti.
        assert _conta_azioni(caso_id, "ACCOGLIENZA") == azioni_accoglienza_prima
        assert _conta_azioni(caso_id, "GUIDA ALLA FOTO") == azioni_foto_prima
        assert _conta_azioni(caso_id, "ANALISI") == 1
    finally:
        connessione.close()


def test_isolamento_tra_due_casi_diversi():
    """Marta (percorso con foto, fermata prima di ANALISI) e Luca (nessuna
    foto, termina subito dopo ACCOGLIENZA) usano thread_id diversi nello
    stesso file di stato: verifica che i due stati salvati restino separati,
    ciascuno con il proprio caso_id e il proprio punto di arresto — non si
    confondono nello stesso file."""
    percorsi = genera_immagini_demo()
    foto_marta_sfocata = percorsi["marta_sfocata"].read_bytes()
    foto_marta_nitida = percorsi["marta_nitida"].read_bytes()

    id_marta = _id_paziente("Marta")
    id_luca = _id_paziente("Luca")
    config_marta = {"configurable": {"thread_id": thread_id_per_paziente(id_marta)}}
    config_luca = {"configurable": {"thread_id": thread_id_per_paziente(id_luca)}}

    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo = costruisci_grafo(checkpointer=SqliteSaver(connessione), interrupt_before=["analisi"])

        esito_marta = grafo.invoke(
            _stato_iniziale(id_marta, foto_da_provare=[foto_marta_sfocata, foto_marta_nitida]), config_marta
        )
        # Luca non ha foto: il suo percorso ("prevenzione") finisce prima di
        # arrivare a guida_alla_foto/analisi, quindi interrupt_before non
        # scatta per lui — termina naturalmente in un'unica invoke().
        esito_luca = grafo.invoke(_stato_iniziale(id_luca), config_luca)

        stato_marta = grafo.get_state(config_marta)
        stato_luca = grafo.get_state(config_luca)

        # Marta: fermata prima di ANALISI, con la sua ripetizione della foto.
        assert stato_marta.next == ("analisi",)
        assert stato_marta.values["percorso_nodi"] == ["ACCOGLIENZA", "GUIDA ALLA FOTO", "GUIDA ALLA FOTO"]
        assert stato_marta.values["caso_id"] == esito_marta["caso_id"]

        # Luca: percorso concluso, nessun nodo in sospeso.
        assert stato_luca.next == ()
        assert stato_luca.values["percorso_nodi"] == ["ACCOGLIENZA"]
        assert stato_luca.values["percorso"] == "prevenzione"
        assert stato_luca.values["caso_id"] == esito_luca["caso_id"]

        # I due stati non si sono mescolati: caso_id diversi, contenuti diversi.
        assert stato_marta.values["caso_id"] != stato_luca.values["caso_id"]
    finally:
        connessione.close()


def test_stato_sopravvive_alla_chiusura_e_riapertura_del_processo():
    """Situazione reale con Streamlit: il processo Python può fermarsi e
    ripartire. Ferma il grafo a metà per Giulia, chiude DAVVERO la
    connessione, poi apre una connessione e un grafo compilato completamente
    nuovi (nessun oggetto Python condiviso con la parte precedente) e verifica
    che lo stato sia ancora lì, identico."""
    percorsi = genera_immagini_demo()
    paziente_id = _id_paziente("Giulia")
    thread_id = thread_id_per_paziente(paziente_id)
    config = {"configurable": {"thread_id": thread_id}}

    # NOTA: la stessa Giulia è già stata fermata prima di ANALISI nel primo
    # test di questo file, sotto lo stesso thread_id — qui si verifica solo
    # che quello stato sia ancora leggibile da una connessione completamente
    # nuova, senza doverlo ricreare.
    connessione_1 = ottieni_connessione_stato_grafo()
    try:
        grafo_1 = costruisci_grafo(checkpointer=SqliteSaver(connessione_1), interrupt_before=["analisi"])
        stato_prima_della_chiusura = grafo_1.get_state(config)
        assert stato_prima_della_chiusura.next == ("analisi",)
    finally:
        connessione_1.close()  # chiusura reale della connessione, non solo del riferimento Python

    # Riapertura "da zero": nuova connessione, nuovo SqliteSaver, nuovo grafo
    # compilato — simula un nuovo avvio del processo Python.
    connessione_2 = ottieni_connessione_stato_grafo()
    try:
        grafo_2 = costruisci_grafo(checkpointer=SqliteSaver(connessione_2), interrupt_before=["analisi"])
        stato_dopo_riapertura = grafo_2.get_state(config)

        assert stato_dopo_riapertura.next == ("analisi",)
        assert stato_dopo_riapertura.values["percorso_nodi"] == stato_prima_della_chiusura.values["percorso_nodi"]
        assert stato_dopo_riapertura.values["caso_id"] == stato_prima_della_chiusura.values["caso_id"]
    finally:
        connessione_2.close()


def test_reset_della_demo_cancella_anche_lo_stato_del_grafo():
    """Richiesta esplicita di Mattia: dopo 'Reimposta demo', un percorso
    fermato a metà nella sessione precedente non deve riemergere. Usa Marta,
    che nel test di isolamento sopra è rimasta fermata prima di ANALISI sotto
    lo stesso thread_id che avrà anche dopo il reset (resetta_database()
    azzera i contatori AUTOINCREMENT e ripopola i pazienti demo sempre nello
    stesso ordine fisso, quindi Marta riottiene lo stesso paziente_id — è
    proprio questo il caso in cui, senza cancella_stato_grafo(), il grafo
    riprenderebbe per errore lo stato di prima del reset)."""
    id_marta_prima_del_reset = _id_paziente("Marta")
    thread_id = thread_id_per_paziente(id_marta_prima_del_reset)
    config = {"configurable": {"thread_id": thread_id}}

    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo = costruisci_grafo(checkpointer=SqliteSaver(connessione))
        # Premessa: prima del reset lo stato fermato a metà è ancora lì
        # (lasciato dal test di isolamento).
        assert grafo.get_state(config).next == ("analisi",)
    finally:
        connessione.close()

    resetta_database()

    id_marta_dopo_il_reset = _id_paziente("Marta")
    assert id_marta_dopo_il_reset == id_marta_prima_del_reset  # premessa del test: stesso id, stesso thread_id

    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo = costruisci_grafo(checkpointer=SqliteSaver(connessione))
        stato_dopo_reset = grafo.get_state(config)
        assert stato_dopo_reset.values == {}
        assert stato_dopo_reset.next == ()

        # Rieseguito da capo, il percorso di Marta riparte dall'ACCOGLIENZA,
        # non da dove si era fermato prima del reset.
        percorsi = genera_immagini_demo()
        foto_sfocata = percorsi["marta_sfocata"].read_bytes()
        foto_nitida = percorsi["marta_nitida"].read_bytes()

        esito = grafo.invoke(
            _stato_iniziale(id_marta_dopo_il_reset, foto_da_provare=[foto_sfocata, foto_nitida]), config
        )

        assert esito["percorso_nodi"] == [
            "ACCOGLIENZA", "GUIDA ALLA FOTO", "GUIDA ALLA FOTO", "ANALISI", "INSTRADAMENTO",
        ]
    finally:
        connessione.close()


if __name__ == "__main__":
    inizializza_database()
    cancella_stato_grafo()

    test_fermo_a_meta_percorso_lo_stato_salvato_indica_il_punto_esatto()
    print("OK - il grafo fermato a metà salva esattamente il punto in cui si trova")

    test_riprende_lesecuzione_senza_rieseguire_i_nodi_gia_completati()
    print("OK - la ripresa prosegue senza rieseguire i nodi già completati")

    test_isolamento_tra_due_casi_diversi()
    print("OK - due casi diversi hanno stati salvati separati")

    test_stato_sopravvive_alla_chiusura_e_riapertura_del_processo()
    print("OK - lo stato sopravvive alla chiusura e riapertura del processo")

    test_reset_della_demo_cancella_anche_lo_stato_del_grafo()
    print("OK - il reset della demo cancella anche lo stato salvato del grafo")

    print("\nTEST SUPERATO")
