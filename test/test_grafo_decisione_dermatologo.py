"""
Test del grafo LangGraph dedicato alla decisione del dermatologo (Fase 3,
passo 3: agenti/decisione_dermatologo.py e
agenti/grafo_decisione_dermatologo.py).

Costruisce i casi con le stesse chiamate dirette agli agenti già usate
dall'interfaccia (pages/paziente.py, non toccata da questo passo): se qualcosa
qui si rompesse, sarebbe un problema di questo nuovo grafo, non del percorso
paziente esistente.

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

from nucleo.database import inizializza_database, ottieni_connessione
from nucleo.dati_demo import genera_immagini_demo
from nucleo.registro_audit import calcola_riepilogo_supervisione_umana
from agenti.accoglienza import valuta_questionario
from agenti.guida_foto import TENTATIVI_MASSIMI, valuta_foto
from agenti.analisi import analizza_caso
from agenti.instradamento import instrada_caso, ottieni_coda_dermatologo
from agenti.decisione_dermatologo import ETICHETTE_AZIONE, ottieni_casi_in_attesa_nuova_foto, ottieni_scheda_caso
from agenti.grafo import cancella_stato_grafo, ottieni_connessione_stato_grafo
from agenti.grafo_decisione_dermatologo import (
    avvia_o_recupera_decisione,
    costruisci_grafo_decisione,
    invia_decisione,
    thread_id_per_caso,
)


def setup_module(module):
    inizializza_database()
    cancella_stato_grafo()


def _id_paziente(nome: str) -> int:
    connessione = ottieni_connessione()
    try:
        riga = connessione.execute("SELECT id FROM pazienti WHERE nome = ?", (nome,)).fetchone()
    finally:
        connessione.close()
    return riga[0]


def _crea_caso_in_coda(nome_paziente: str, chiave_foto: str) -> int:
    """Un caso destinato al dermatologo, con la stessa sequenza di chiamate
    dirette usata oggi da pages/paziente.py: valuta_questionario, valuta_foto,
    analizza_caso, instrada_caso."""
    percorsi = genera_immagini_demo()
    foto = percorsi[chiave_foto].read_bytes()
    paziente_id = _id_paziente(nome_paziente)

    caso_id = valuta_questionario(paziente_id)["caso_id"]
    valuta_foto(caso_id, foto)
    esito_analisi = analizza_caso(caso_id)
    assert esito_analisi["destinato_dermatologo"] is True  # premessa del test
    instrada_caso(caso_id)
    return caso_id


def _crea_caso_qualita_insufficiente(nome_paziente: str, chiave_foto_scarsa: str) -> int:
    """Un caso accettato dopo 3 tentativi falliti (regola di non esclusione,
    agenti/guida_foto.py), che finisce comunque in coda con l'etichetta di
    qualità insufficiente."""
    percorsi = genera_immagini_demo()
    foto_scarsa = percorsi[chiave_foto_scarsa].read_bytes()
    paziente_id = _id_paziente(nome_paziente)

    caso_id = valuta_questionario(paziente_id)["caso_id"]
    risultato = None
    for _ in range(TENTATIVI_MASSIMI):
        risultato = valuta_foto(caso_id, foto_scarsa)
    assert risultato["qualita_insufficiente_forzata"] is True  # premessa del test

    esito_analisi = analizza_caso(caso_id)
    assert esito_analisi["destinato_dermatologo"] is True
    instrada_caso(caso_id)
    return caso_id


def test_etichetta_procedi_televisita_non_contiene_piu_approva():
    """Guardia contro regressioni (passo 3.4): un'etichetta con 'approva'
    invita a confermare senza dichiarare l'azione — esattamente l'inerzia che
    il principio 'nessun valore preselezionato su un dato clinico' vuole
    evitare (CLAUDE.md, sezione 3). Il valore interno resta invariato."""
    assert "approva" not in ETICHETTE_AZIONE["approva_televisita"].lower()


def test_caso_destinato_al_dermatologo_sospende_il_grafo_prima_della_decisione():
    caso_id = _crea_caso_in_coda("Marta", "marta_nitida")

    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo = costruisci_grafo_decisione(checkpointer=SqliteSaver(connessione))
        avvia_o_recupera_decisione(grafo, caso_id)

        config = {"configurable": {"thread_id": thread_id_per_caso(caso_id)}}
        stato_salvato = grafo.get_state(config)

        assert stato_salvato.next == ("decisione_dermatologo",)
        assert stato_salvato.values["caso_id"] == caso_id
        assert stato_salvato.values["azione_scelta"] is None
    finally:
        connessione.close()


def test_ciascuna_decisione_fa_riprendere_il_grafo_e_produce_leffetto_corretto():
    riepilogo_prima = calcola_riepilogo_supervisione_umana()["conteggi"]

    # Ogni scenario è creato e deciso PRIMA di passare al successivo (mai due
    # casi aperti insieme per lo stesso paziente/lesione): la ricerca
    # "ultima classificazione per questa lesione" — sia qui che nel codice già
    # esistente di agenti/followup.py — assume un solo caso attivo alla volta
    # per lesione (stessa semplificazione già documentata al passo 3.2).
    # Creare due casi sovrapposti per Paolo o Giulia prima di decidere sul
    # primo farebbe leggere la classificazione del caso sbagliato.
    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo = costruisci_grafo_decisione(checkpointer=SqliteSaver(connessione))

        def _decidi(caso_id, azione, decisione_attesa):
            avvia_o_recupera_decisione(grafo, caso_id)
            esito = invia_decisione(grafo, caso_id, azione)
            assert esito["esito"]["azione_scelta"] == azione
            assert esito["esito"]["decisione"] == decisione_attesa
            config = {"configurable": {"thread_id": thread_id_per_caso(caso_id)}}
            assert grafo.get_state(config).next == ()  # il grafo è arrivato in fondo, non più in pausa

        caso_biopsia = _crea_caso_in_coda("Marta", "marta_nitida")  # classificatore: sospetta
        _decidi(caso_biopsia, "richiedi_biopsia", "approvato")

        caso_nuova_foto = _crea_caso_in_coda("Paolo", "paolo_nitida")  # classificatore: non conclusiva
        _decidi(caso_nuova_foto, "richiedi_nuova_foto", "approvato")

        caso_approva = _crea_caso_in_coda("Giulia", "giulia_nitida")  # classificatore: probabilmente benigna
        _decidi(caso_approva, "approva_televisita", "approvato")

        caso_chiudi = _crea_caso_in_coda("Giulia", "giulia_nitida")
        _decidi(caso_chiudi, "chiudi_caso", "modificato")  # il sistema non propone mai di chiudere: sempre "modificato"

        caso_ambulatorio = _crea_caso_qualita_insufficiente("Paolo", "marta_risoluzione_bassa")
        _decidi(caso_ambulatorio, "convoca_ambulatorio", "approvato")
    finally:
        connessione.close()

    connessione = ottieni_connessione()
    try:
        def _leggi_stato(caso_id):
            return connessione.execute("SELECT stato FROM casi WHERE id = ?", (caso_id,)).fetchone()[0]

        stato_biopsia = _leggi_stato(caso_biopsia)
        esiste_biopsia = connessione.execute(
            "SELECT 1 FROM appuntamenti WHERE caso_id = ? AND tipo = 'biopsia'", (caso_biopsia,)
        ).fetchone() is not None
        stato_nuova_foto = _leggi_stato(caso_nuova_foto)
        stato_approva = _leggi_stato(caso_approva)
        stato_chiudi = _leggi_stato(caso_chiudi)
        stato_ambulatorio = _leggi_stato(caso_ambulatorio)
    finally:
        connessione.close()

    # "richiedi_biopsia" non cambia casi.stato: il caso esce dalla coda perché
    # ha un appuntamento di biopsia (agenti/instradamento.py, invariato).
    assert stato_biopsia == "in_coda_dermatologo"
    assert esiste_biopsia is True
    assert stato_nuova_foto == "attesa_nuova_foto"
    assert stato_approva == "approvato_televisita"
    assert stato_chiudi == "chiuso_senza_accertamenti"
    assert stato_ambulatorio == "convocato_ambulatorio"

    # Il caso "richiedi nuova foto" compare nella sezione dedicata (ben
    # etichettato: non richiede una valutazione clinica ora), non nella coda
    # ordinaria — condizione esplicita posta da Mattia per questo passo.
    casi_in_attesa_foto = ottieni_casi_in_attesa_nuova_foto()
    assert any(c["caso_id"] == caso_nuova_foto for c in casi_in_attesa_foto)

    coda = ottieni_coda_dermatologo()
    id_in_coda = {c["caso_id"] for c in coda}
    assert caso_nuova_foto not in id_in_coda
    assert caso_approva not in id_in_coda
    assert caso_chiudi not in id_in_coda
    assert caso_ambulatorio not in id_in_coda
    assert caso_biopsia not in id_in_coda  # esclusa perché ha una biopsia, come già oggi

    riepilogo_dopo = calcola_riepilogo_supervisione_umana()["conteggi"]
    assert riepilogo_dopo["approvato"] - riepilogo_prima["approvato"] == 4
    assert riepilogo_dopo["modificato"] - riepilogo_prima["modificato"] == 1


def test_giulia_sistema_propone_procedere_dermatologo_chiede_biopsia_grafo_riprende():
    """Lo scenario indicato esplicitamente da Mattia: il sistema propone di
    procedere con la televisita, il dermatologo chiede invece una biopsia, il
    grafo riprende e registra la modifica."""
    caso_id = _crea_caso_in_coda("Giulia", "giulia_nitida")

    scheda = ottieni_scheda_caso(caso_id)
    assert scheda["proposta_sistema"] == "approva_televisita"

    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo = costruisci_grafo_decisione(checkpointer=SqliteSaver(connessione))
        avvia_o_recupera_decisione(grafo, caso_id)

        config = {"configurable": {"thread_id": thread_id_per_caso(caso_id)}}
        assert grafo.get_state(config).next == ("decisione_dermatologo",)

        esito = invia_decisione(grafo, caso_id, "richiedi_biopsia")

        assert esito["esito"]["proposta_sistema"] == "approva_televisita"
        assert esito["esito"]["azione_scelta"] == "richiedi_biopsia"
        assert esito["esito"]["decisione"] == "modificato"
        assert grafo.get_state(config).next == ()
    finally:
        connessione.close()

    connessione = ottieni_connessione()
    try:
        riga = connessione.execute(
            """SELECT proposta_sistema, azione_scelta, decisione FROM decisioni_dermatologo
               WHERE caso_id = ? ORDER BY id DESC LIMIT 1""",
            (caso_id,),
        ).fetchone()
        esiste_biopsia = connessione.execute(
            "SELECT 1 FROM appuntamenti WHERE caso_id = ? AND tipo = 'biopsia'", (caso_id,)
        ).fetchone() is not None
    finally:
        connessione.close()

    assert riga == ("approva_televisita", "richiedi_biopsia", "modificato")
    assert esiste_biopsia is True


def test_caso_con_qualita_insufficiente_puo_essere_convocato_in_ambulatorio():
    caso_id = _crea_caso_qualita_insufficiente("Marta", "marta_risoluzione_bassa")

    scheda = ottieni_scheda_caso(caso_id)
    assert scheda["qualita_foto_insufficiente"] is True
    assert scheda["proposta_sistema"] == "convoca_ambulatorio"

    connessione = ottieni_connessione_stato_grafo()
    try:
        grafo = costruisci_grafo_decisione(checkpointer=SqliteSaver(connessione))
        avvia_o_recupera_decisione(grafo, caso_id)
        esito = invia_decisione(grafo, caso_id, "convoca_ambulatorio")
        assert esito["esito"]["decisione"] == "approvato"
    finally:
        connessione.close()

    connessione = ottieni_connessione()
    try:
        stato = connessione.execute("SELECT stato FROM casi WHERE id = ?", (caso_id,)).fetchone()[0]
    finally:
        connessione.close()
    assert stato == "convocato_ambulatorio"


if __name__ == "__main__":
    inizializza_database()
    cancella_stato_grafo()

    test_etichetta_procedi_televisita_non_contiene_piu_approva()
    print("OK - l'etichetta 'procedi con la televisita' non contiene più la parola 'approva'")

    test_caso_destinato_al_dermatologo_sospende_il_grafo_prima_della_decisione()
    print("OK - un caso in coda sospende il grafo prima della decisione")

    test_ciascuna_decisione_fa_riprendere_il_grafo_e_produce_leffetto_corretto()
    print("OK - ciascuna delle 5 decisioni riprende il grafo e produce l'effetto corretto")

    test_giulia_sistema_propone_procedere_dermatologo_chiede_biopsia_grafo_riprende()
    print("OK - Giulia: proposta 'approva televisita', il dermatologo chiede la biopsia, il grafo riprende")

    test_caso_con_qualita_insufficiente_puo_essere_convocato_in_ambulatorio()
    print("OK - un caso con qualità foto insufficiente può essere convocato in ambulatorio")

    print("\nTEST SUPERATO")
