"""
Grafo LangGraph dedicato al tratto che richiede l'intervento umano: la
decisione del dermatologo su un caso in coda (Fase 3, passo 3).

SCELTA IMPLEMENTATIVA, NON NECESSITÀ ARCHITETTURALE: questo è un grafo
SEPARATO da agenti/grafo.py (il grafo a 5 nodi dei passi 3.1/3.2), non
un'estensione di quello. La separazione è stata scelta per non rischiare di
rompere quel grafo già verificato e i suoi test (test/test_grafo.py,
test/test_persistenza_grafo.py), non perché i due debbano restare per forza
distinti: sarebbero unificabili — un unico grafo, con questo nodo aggiunto
dopo instradamento — se in futuro servisse davvero (vedi CLAUDE.md, sezione 9).
Non prendere questa separazione come un vincolo architetturale permanente.

Diversamente da agenti/grafo.py, qui l'identificativo di esecuzione (thread_id)
è basato su caso_id, non su paziente_id: il caso esiste già quando questo
grafo viene invocato per la prima volta (è già passato da ACCOGLIENZA, GUIDA
ALLA FOTO, ANALISI e INSTRADAMENTO, tutti gestiti direttamente
dall'interfaccia — vedi pages/paziente.py, non toccata da questo passo), quindi
qui non c'è il problema "il caso non esiste ancora" che in agenti/grafo.py ha
portato a usare paziente_id (vedi il commento su thread_id_per_paziente lì).

L'interruzione (interrupt_before) è SEMPRE attiva qui, non un parametro
opzionale per i soli test come in agenti/grafo.py: è l'intero scopo di questo
grafo, sospendersi prima che qualcuno decida.

Riusa il file di stato salvato già esistente (data/stato_grafo.db,
agenti/grafo.py::ottieni_connessione_stato_grafo): i thread_id non collidono
mai ("caso-<id>" qui, "paziente-<id>" nell'altro grafo), e
agenti/grafo.py::cancella_stato_grafo (usata dal reset della demo) pulisce già
entrambi senza bisogno di modifiche.
"""

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from agenti.decisione_dermatologo import decidi_e_applica


def thread_id_per_caso(caso_id: int) -> str:
    """Identificativo di esecuzione per il checkpointer di questo grafo:
    ricavabile direttamente dal caso stesso — a differenza di
    agenti/grafo.py::thread_id_per_paziente, qui non serve nessuna scelta di
    compromesso, perché il caso esiste già quando si invoca questo grafo."""
    return f"caso-{caso_id}"


class StatoDecisioneDermatologo(TypedDict):
    """Stato minimo: nessun dato clinico duplicato qui (resta nel database,
    letto e scritto da agenti/decisione_dermatologo.py) — solo ciò che serve
    al nodo per sapere quale caso decidere e con quale scelta."""

    caso_id: int
    azione_scelta: str | None  # None finché il dermatologo non ha ancora deciso
    esito: dict | None
    percorso_nodi: Annotated[list[str], operator.add]


def nodo_decisione_dermatologo(stato: StatoDecisioneDermatologo) -> dict:
    esito = decidi_e_applica(stato["caso_id"], stato["azione_scelta"])
    return {"esito": esito, "percorso_nodi": ["DECISIONE DERMATOLOGO"]}


def costruisci_grafo_decisione(*, checkpointer=None):
    """Costruisce e compila il grafo. interrupt_before è SEMPRE attivo (non un
    parametro esposto): questo grafo esiste solo per sospendersi prima della
    decisione, non avrebbe senso costruirlo senza."""
    grafo = StateGraph(StatoDecisioneDermatologo)
    grafo.add_node("decisione_dermatologo", nodo_decisione_dermatologo)
    grafo.add_edge(START, "decisione_dermatologo")
    grafo.add_edge("decisione_dermatologo", END)
    return grafo.compile(checkpointer=checkpointer, interrupt_before=["decisione_dermatologo"])


def _stato_iniziale(caso_id: int) -> StatoDecisioneDermatologo:
    return {"caso_id": caso_id, "azione_scelta": None, "esito": None, "percorso_nodi": []}


def avvia_o_recupera_decisione(grafo, caso_id: int) -> dict:
    """Assicura che il grafo sia in pausa in attesa della decisione per questo
    caso: lo avvia se non era mai stato invocato; se lo era già, invocarlo di
    nuovo con input "fresco" su un thread già in pausa è innocuo (verificato:
    non riesegue nulla, non lo corrompe). Restituisce lo stato attuale. Usato
    dalla pagina Dermatologo quando si apre la scheda di un caso — è questo il
    momento in cui il grafo si sospende davvero, in attesa di chi deciderà."""
    config = {"configurable": {"thread_id": thread_id_per_caso(caso_id)}}
    grafo.invoke(_stato_iniziale(caso_id), config)
    return grafo.get_state(config).values


def invia_decisione(grafo, caso_id: int, azione_scelta: str) -> dict:
    """Inietta la decisione del dermatologo nello stato fermato e riprende
    l'esecuzione: il nodo decisione_dermatologo gira una sola volta, con la
    decisione già dentro lo stato (vedi agenti/decisione_dermatologo.py per
    gli effetti applicati)."""
    config = {"configurable": {"thread_id": thread_id_per_caso(caso_id)}}
    grafo.update_state(config, {"azione_scelta": azione_scelta})
    return grafo.invoke(None, config)


if __name__ == "__main__":
    # Rigenera il diagramma Mermaid di QUESTO grafo per la presentazione, come
    # già fa agenti/grafo.py per l'altro: `python -m agenti.grafo_decisione_dermatologo`.
    from pathlib import Path

    cartella_progetto = Path(__file__).resolve().parent.parent
    cartella_presentazione = cartella_progetto / "presentazione"
    cartella_presentazione.mkdir(parents=True, exist_ok=True)
    percorso_diagramma = cartella_presentazione / "grafo_decisione_dermatologo.mmd"

    diagramma_mermaid = costruisci_grafo_decisione().get_graph().draw_mermaid()
    percorso_diagramma.write_text(diagramma_mermaid, encoding="utf-8")

    print(f"Diagramma salvato in {percorso_diagramma}")
    print()
    print(diagramma_mermaid)
