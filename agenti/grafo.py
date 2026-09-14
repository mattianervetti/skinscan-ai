"""
Grafo LangGraph che collega i cinque agenti (Fase 3, passo 1).

PRINCIPIO FONDAMENTALE: questo modulo non prende NESSUNA decisione clinica e
non reimplementa NESSUNA regola. Ogni nodo chiama SOLO la funzione già
esistente e già testata dell'agente corrispondente (agenti/accoglienza.py,
agenti/guida_foto.py, agenti/analisi.py, agenti/instradamento.py,
agenti/followup.py); nessuno di quei file viene toccato da questo passo.

Le condizioni degli archi leggono il risultato che l'agente ha già calcolato
(percorso, destinato_dermatologo, accettata, ...) — non richiamano di nuovo
nucleo/regole_sicurezza.py. Quel modulo viene chiamato una sola volta, dentro
l'agente: la regola resta scritta in un solo posto, e se cambia cambia lì.
Rifare qui la stessa decisione (es. richiamare decidi_percorso con priorità e
neo_cambiato) significherebbe avere due punti da tenere sincronizzati per la
stessa regola — esattamente il difetto da evitare.

NON ANCORA IMPLEMENTATO IN QUESTO PASSO (arriveranno nei prossimi due passi
della Fase 3): il meccanismo di interruzione per l'approvazione del
dermatologo, e la persistenza dello stato tra una chiamata e l'altra. Il
grafo, per ora, esegue dall'inizio alla fine in un'unica chiamata a invoke().

NON ANCORA COLLEGATO ALL'INTERFACCIA: pages/*.py e app.py continuano a
chiamare gli agenti direttamente, esattamente come oggi. Questo modulo esiste
accanto al sistema che funziona, non lo sostituisce.

PERSISTENZA DELLO STATO (Fase 3, passo 2): costruisci_grafo() accetta ora due
parametri opzionali, checkpointer e interrupt_before, entrambi None di
default — con i default, il comportamento è IDENTICO al passo 1 (nessuna
persistenza, esecuzione dall'inizio alla fine in un'unica invoke()), quindi i
test del passo 1 restano validi senza modifiche. Il salvataggio vero e proprio
usa langgraph-checkpoint-sqlite (SqliteSaver), in un file SEPARATO dal database
clinico (data/stato_grafo.db): quel file ha uno schema tecnico gestito in
automatico dalla libreria, che non ha nulla a che fare con
nucleo.database.VERSIONE_SCHEMA.

NON ANCORA IMPLEMENTATO: il meccanismo di interruzione per l'approvazione del
dermatologo (arriva al passo 3.3). Il parametro interrupt_before esposto qui è
la funzionalità già pronta di LangGraph usata SOLO nei test di questo passo,
per verificare che lo stato salvato sia corretto fermando il grafo a metà in
modo controllato — non è ancora il meccanismo di human-in-the-loop.
"""

import operator
import sqlite3
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from agenti.accoglienza import valuta_questionario
from agenti.analisi import analizza_caso
from agenti.followup import carica_esito_istologico
from agenti.guida_foto import valuta_foto
from agenti.instradamento import instrada_caso

# File SQLite dedicato allo stato salvato del grafo (checkpointer), separato dal
# database clinico (data/skinscan.db). Stesso stile di calcolo del percorso già
# usato in nucleo/database.py: relativo alla cartella del progetto, funziona
# identico su Windows e su Linux (Streamlit Community Cloud).
_CARTELLA_PROGETTO = Path(__file__).resolve().parent.parent
PERCORSO_DATABASE_GRAFO = _CARTELLA_PROGETTO / "data" / "stato_grafo.db"


def ottieni_connessione_stato_grafo() -> sqlite3.Connection:
    """Apre una connessione al file dello stato salvato del grafo, creando la
    cartella data/ se non esiste. check_same_thread=False perché Streamlit può
    eseguire il codice da thread diversi tra un'interazione e l'altra;
    SqliteSaver gestisce comunque l'accesso in sicurezza con un lucchetto
    interno (threading.Lock), quindi due operazioni non si accavallano mai."""
    PERCORSO_DATABASE_GRAFO.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(PERCORSO_DATABASE_GRAFO, check_same_thread=False)


def cancella_stato_grafo() -> None:
    """Cancella il file dello stato salvato del grafo (e gli eventuali file
    di supporto della modalità WAL, -wal e -shm). Va richiamata da
    nucleo.database.resetta_database(): senza questo passaggio, dopo un reset
    della demo il grafo riprenderebbe il percorso a metà della sessione
    precedente invece di ripartire da capo — un problema concreto per una
    demo che va rifatta più volte, non solo teorico."""
    for suffisso in ("", "-wal", "-shm"):
        percorso = PERCORSO_DATABASE_GRAFO.with_name(PERCORSO_DATABASE_GRAFO.name + suffisso)
        if percorso.exists():
            percorso.unlink()


def thread_id_per_paziente(paziente_id: int) -> str:
    """Identificativo di esecuzione (thread_id) per il checkpointer del grafo.

    LIMITE CONSAPEVOLE, da riconsiderare se in futuro un paziente potesse avere
    più percorsi/lesioni monitorati in parallelo (non oggi: nessuno dei 4
    pazienti demo lo fa): un solo percorso attivo per paziente alla volta. Non
    si usa caso_id perché il caso non esiste ancora quando il grafo parte (lo
    crea il nodo ACCOGLIENZA stesso, chiamando valuta_questionario) — non si
    può ricavare un identificativo da qualcosa che non esiste ancora alla
    prima chiamata. paziente_id invece è disponibile fin dall'inizio, ed è
    comunque ricavabile a partire da un caso già aperto (ogni riga della
    tabella casi contiene il proprio paziente_id)."""
    return f"paziente-{paziente_id}"


class StatoGrafo(TypedDict):
    """Stato minimo: solo ciò che serve a un nodo per decidere cosa fare o a
    un arco per decidere dove andare. I dati veri (questionario, foto,
    classificazione, ecc.) restano nel database — li scrive già l'agente
    chiamato da ogni nodo, non li duplichiamo qui."""

    paziente_id: int
    caso_id: int | None

    # 'foto' / 'prevenzione' e destinazione al dermatologo: già decisi da
    # nucleo.regole_sicurezza dentro valuta_questionario() e analizza_caso().
    # Il grafo li LEGGE, non li ricalcola (vedi principio in cima al file).
    percorso: str | None
    destinato_dermatologo: bool

    # Coda di foto da tentare, consumata una alla volta dal nodo GUIDA ALLA
    # FOTO a ogni ripetizione. STAND-IN TEMPORANEO per l'input reale del
    # paziente: senza un meccanismo di interruzione (non ancora implementato,
    # arriva nel passo 3.3 della Fase 3), il grafo non può fermarsi ad
    # aspettare una foto nuova da chi scatta — quindi per ora le foto da
    # provare vengono fornite in anticipo da chi invoca il grafo (nei test,
    # dati_demo). NON è una scelta di architettura definitiva: quando ci sarà
    # l'interruzione, questo campo sparirà e il nodo aspetterà davvero il
    # paziente.
    foto_da_provare: list[bytes]
    foto_accettata: bool
    foto_qualita_insufficiente_forzata: bool

    # Se valorizzato, dopo INSTRADAMENTO si passa a FOLLOW-UP per registrare
    # questo esito. Presuppone che una biopsia sia già stata richiesta PRIMA
    # di invocare il grafo (decisione del dermatologo, oggi un pulsante
    # nell'interfaccia — resta fuori dal grafo anche in questo passo).
    esito_istologico_da_caricare: str | None

    # Traccia dei nodi visitati, in ordine: serve ai test per verificare che
    # il grafo abbia seguito il percorso atteso (es. che GUIDA ALLA FOTO sia
    # stato visitato due volte per Marta). Annotated con operator.add: ogni
    # nodo AGGIUNGE il proprio nome, invece di sovrascrivere la lista.
    percorso_nodi: Annotated[list[str], operator.add]


def nodo_accoglienza(stato: StatoGrafo) -> dict:
    esito = valuta_questionario(stato["paziente_id"])
    return {
        "caso_id": esito["caso_id"],
        "percorso": esito["percorso"],
        "destinato_dermatologo": esito["destinato_dermatologo"],
        "percorso_nodi": ["ACCOGLIENZA"],
    }


def nodo_guida_alla_foto(stato: StatoGrafo) -> dict:
    foto_rimanenti = list(stato["foto_da_provare"])
    # Se le foto fornite finiscono prima che una venga accettata, si ripete
    # l'ultima: valuta_foto() forza comunque l'accettazione dopo
    # TENTATIVI_MASSIMI tentativi (regola di non esclusione, già nell'agente),
    # quindi il ciclo termina sempre.
    dati_immagine = foto_rimanenti.pop(0) if foto_rimanenti else stato["foto_da_provare"][-1]

    esito = valuta_foto(stato["caso_id"], dati_immagine)

    return {
        "foto_da_provare": foto_rimanenti,
        "foto_accettata": esito["accettata"],
        "foto_qualita_insufficiente_forzata": esito["qualita_insufficiente_forzata"],
        "percorso_nodi": ["GUIDA ALLA FOTO"],
    }


def nodo_analisi(stato: StatoGrafo) -> dict:
    esito = analizza_caso(stato["caso_id"])
    return {
        # Può passare da False a True (mai il contrario: l'agente non
        # "retrocede" mai un caso già destinato — vedi CLAUDE.md sezione 5).
        "destinato_dermatologo": esito["destinato_dermatologo"],
        "percorso_nodi": ["ANALISI"],
    }


def nodo_instradamento(stato: StatoGrafo) -> dict:
    instrada_caso(stato["caso_id"])
    return {"percorso_nodi": ["INSTRADAMENTO"]}


def nodo_followup(stato: StatoGrafo) -> dict:
    carica_esito_istologico(stato["caso_id"], stato["esito_istologico_da_caricare"])
    return {"percorso_nodi": ["FOLLOW-UP"]}


def _dopo_accoglienza(stato: StatoGrafo) -> str:
    # percorso è già il risultato di nucleo.regole_sicurezza.decidi_percorso
    # (chiamato dentro valuta_questionario): qui si legge, non si ricalcola.
    return END if stato["percorso"] == "prevenzione" else "guida_alla_foto"


def _dopo_guida_alla_foto(stato: StatoGrafo) -> str:
    if stato["foto_accettata"] or stato["foto_qualita_insufficiente_forzata"]:
        return "analisi"
    return "guida_alla_foto"


def _dopo_analisi(stato: StatoGrafo) -> str:
    # destinato_dermatologo è già il risultato di
    # nucleo.regole_sicurezza.decidi_destinazione_dopo_analisi (chiamato
    # dentro analizza_caso): instrada_caso() solleva un errore se il caso non
    # è 'in_coda_dermatologo', quindi qui la condizione è obbligatoria, non
    # solo un'ottimizzazione.
    return "instradamento" if stato["destinato_dermatologo"] else END


def _dopo_instradamento(stato: StatoGrafo) -> str:
    return "followup" if stato.get("esito_istologico_da_caricare") else END


def costruisci_grafo(*, checkpointer=None, interrupt_before=None):
    """Costruisce e compila il grafo.

    Con i parametri di default (checkpointer=None, interrupt_before=None) il
    comportamento è identico al passo 1: il grafo esegue dall'inizio alla fine
    in un'unica chiamata a invoke(), senza persistenza. Tutte le chiamate
    esistenti (test del passo 1, eventuale uso futuro senza persistenza)
    restano quindi valide senza modifiche.

    checkpointer: un'istanza di SqliteSaver (langgraph.checkpoint.sqlite) per
    salvare e riprendere lo stato tra una chiamata e l'altra. Va costruita e
    chiusa da chi chiama, sulla connessione ottenuta da
    ottieni_connessione_stato_grafo() — questo modulo non tiene mai aperta una
    connessione tra una chiamata e l'altra.

    interrupt_before: elenco di nomi di nodi prima dei quali fermarsi. Usato
    SOLO nei test di questo passo per verificare lo stato salvato fermando il
    grafo a metà in modo controllato; non è il meccanismo di
    human-in-the-loop per il dermatologo (passo 3.3)."""
    grafo = StateGraph(StatoGrafo)

    grafo.add_node("accoglienza", nodo_accoglienza)
    grafo.add_node("guida_alla_foto", nodo_guida_alla_foto)
    grafo.add_node("analisi", nodo_analisi)
    grafo.add_node("instradamento", nodo_instradamento)
    grafo.add_node("followup", nodo_followup)

    grafo.add_edge(START, "accoglienza")
    grafo.add_conditional_edges(
        "accoglienza", _dopo_accoglienza, {"guida_alla_foto": "guida_alla_foto", END: END}
    )
    grafo.add_conditional_edges(
        "guida_alla_foto", _dopo_guida_alla_foto, {"analisi": "analisi", "guida_alla_foto": "guida_alla_foto"}
    )
    grafo.add_conditional_edges(
        "analisi", _dopo_analisi, {"instradamento": "instradamento", END: END}
    )
    grafo.add_conditional_edges(
        "instradamento", _dopo_instradamento, {"followup": "followup", END: END}
    )
    grafo.add_edge("followup", END)

    return grafo.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)


if __name__ == "__main__":
    # Rigenera il diagramma Mermaid del grafo per la presentazione: estratto
    # dal grafo compilato (langgraph), non disegnato a mano — da rilanciare
    # ogni volta che la struttura del grafo cambia.
    from pathlib import Path

    cartella_progetto = Path(__file__).resolve().parent.parent
    cartella_presentazione = cartella_progetto / "presentazione"
    cartella_presentazione.mkdir(parents=True, exist_ok=True)
    percorso_diagramma = cartella_presentazione / "grafo_agenti.mmd"

    diagramma_mermaid = costruisci_grafo().get_graph().draw_mermaid()
    percorso_diagramma.write_text(diagramma_mermaid, encoding="utf-8")

    print(f"Diagramma salvato in {percorso_diagramma}")
    print()
    print(diagramma_mermaid)
