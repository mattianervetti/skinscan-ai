"""
Classificatore SIMULATO delle lesioni cutanee.

ATTENZIONE: questo modulo è una SIMULAZIONE a scopo dimostrativo. NON esegue
alcuna analisi reale dell'immagine: gli esiti sono predefiniti per le immagini
demo, oppure derivati in modo deterministico dall'hash dell'immagine per
immagini sconosciute. Prima di qualunque uso clinico reale, questo file va
sostituito con l'integrazione a un servizio di analisi dermatologica
certificato — l'interfaccia di analizza_lesione() è pensata apposta per
rendere quella sostituzione un cambio di un solo file.

Rischio di ancoraggio numerico: un punteggio di confidenza come 0.88, per quanto
etichettato come simulato, tende a essere percepito come più affidabile di
quanto sia (bias noto in ambito clinico). Per questo ogni esito include un
avviso di simulazione (AVVISO_SIMULAZIONE) che deve viaggiare SEMPRE insieme al
dato, mai separato: chi mostra classificazione/confidenza (in particolare la
futura scheda del dermatologo) deve mostrare l'avviso accanto, non in fondo alla
pagina.
"""

import hashlib
import random

CLASSIFICAZIONI_POSSIBILI = ("sospetta", "probabilmente_benigna", "non_conclusiva")

AVVISO_SIMULAZIONE = (
    "Esito generato da un classificatore SIMULATO a scopo dimostrativo — "
    "non è un'analisi clinica reale."
)


def _hash_immagine(dati_immagine: bytes) -> str:
    return hashlib.sha256(dati_immagine).hexdigest()


def _carica_preset_demo() -> dict[str, dict]:
    """Costruisce la tabella di esiti predefiniti per le immagini demo, con
    chiave l'hash del contenuto (non il nome del file): letta da
    data/demo/immagini al primo utilizzo, così l'associazione resta corretta
    anche se le immagini demo vengono rigenerate con parametri diversi."""
    from nucleo.dati_demo import genera_immagini_demo

    percorsi = genera_immagini_demo()
    preset = {}

    preset[_hash_immagine(percorsi["marta_nitida"].read_bytes())] = {
        "classificazione": "sospetta",
        "confidenza": 0.88,
        "caratteristiche": {
            "diametro_stimato_mm": 8,
            "asimmetria": "marcata",
            "bordi": "irregolari",
            "colore": "non uniforme, aree più scure",
        },
    }
    preset[_hash_immagine(percorsi["marta_precedente"].read_bytes())] = {
        "classificazione": "sospetta",
        "confidenza": 0.81,
        "caratteristiche": {
            "diametro_stimato_mm": 4,
            "asimmetria": "lieve",
            "bordi": "regolari",
            "colore": "abbastanza uniforme",
        },
    }
    preset[_hash_immagine(percorsi["giulia_nitida"].read_bytes())] = {
        "classificazione": "probabilmente_benigna",
        "confidenza": 0.91,
        "caratteristiche": {
            "diametro_stimato_mm": 3,
            "asimmetria": "simmetrica",
            "bordi": "regolari",
            "colore": "uniforme",
        },
    }
    preset[_hash_immagine(percorsi["paolo_nitida"].read_bytes())] = {
        "classificazione": "non_conclusiva",
        "confidenza": 0.42,
        "caratteristiche": {
            "diametro_stimato_mm": 5,
            "asimmetria": "non determinabile",
            "bordi": "parzialmente visibili",
            "colore": "non determinabile",
        },
    }
    return preset


_preset_demo_caricato = None  # caricato al primo utilizzo (lazy), non all'import del modulo


def _ottieni_preset_demo() -> dict[str, dict]:
    global _preset_demo_caricato
    if _preset_demo_caricato is None:
        _preset_demo_caricato = _carica_preset_demo()
    return _preset_demo_caricato


def _esito_deterministico_da_hash(impronta: str) -> dict:
    """Per immagini non presenti nel preset demo: esito derivato in modo
    deterministico dall'hash. random.Random(seed) con seed=impronta produce
    sempre la stessa sequenza per lo stesso hash: stesso input, stesso esito,
    ogni volta — mai un risultato casuale non riproducibile."""
    generatore = random.Random(impronta)
    return {
        "classificazione": generatore.choice(CLASSIFICAZIONI_POSSIBILI),
        "confidenza": round(generatore.uniform(0.5, 0.95), 2),
        "caratteristiche": {
            "diametro_stimato_mm": generatore.randint(2, 10),
            "asimmetria": generatore.choice(["simmetrica", "lieve", "marcata"]),
            "bordi": generatore.choice(["regolari", "irregolari"]),
            "colore": generatore.choice(["uniforme", "non uniforme"]),
        },
    }


def analizza_lesione(dati_immagine: bytes) -> dict:
    """Analizza (in modo SIMULATO) una foto di una lesione cutanea.

    Interfaccia pensata per essere identica a quella di un servizio di analisi
    dermatologica certificato di terzi: riceve SOLO i byte dell'immagine,
    nessun altro parametro.

    Restituisce:
        {"classificazione": "sospetta"/"probabilmente_benigna"/"non_conclusiva",
         "confidenza": float (0-1),
         "caratteristiche": dict,
         "impronta_immagine": str (hash sha256),
         "avviso_simulazione": str}

    L'esito è associato all'impronta (hash) dell'immagine, non al nome del
    file: per le immagini demo è predefinito e stabile; per immagini
    sconosciute è derivato in modo deterministico dall'hash, quindi ripetibile
    ma mai casuale a ogni chiamata.
    """
    impronta = _hash_immagine(dati_immagine)
    preset = _ottieni_preset_demo()
    risultato = dict(preset[impronta]) if impronta in preset else _esito_deterministico_da_hash(impronta)
    risultato["impronta_immagine"] = impronta
    risultato["avviso_simulazione"] = AVVISO_SIMULAZIONE
    return risultato


def confronta_con_precedente(esito_attuale: dict, esito_precedente: dict) -> dict:
    """Confronto SIMULATO tra l'esito attuale e quello di una foto precedente
    della stessa lesione. Restituisce un'informazione descrittiva ESPLICITA per
    il dermatologo (fatti misurati, non un giudizio clinico).

    NON fa parte dell'interfaccia "sostituibile 1:1 con un vendor esterno"
    (quella è solo analizza_lesione): è logica di supporto dell'agente ANALISI,
    tenuta in questo file perché anch'essa simulata e da dichiarare come tale.
    """
    c_attuale = esito_attuale.get("caratteristiche", {})
    c_precedente = esito_precedente.get("caratteristiche", {})

    variazioni = []

    diametro_precedente = c_precedente.get("diametro_stimato_mm")
    diametro_attuale = c_attuale.get("diametro_stimato_mm")
    if (
        isinstance(diametro_precedente, (int, float))
        and isinstance(diametro_attuale, (int, float))
        and diametro_precedente != diametro_attuale
    ):
        variazioni.append(f"diametro stimato variato da {diametro_precedente}mm a {diametro_attuale}mm")

    if c_precedente.get("colore") != c_attuale.get("colore"):
        variazioni.append(
            f"colore descritto come \"{c_precedente.get('colore')}\" in precedenza, ora \"{c_attuale.get('colore')}\""
        )

    if c_precedente.get("bordi") != c_attuale.get("bordi"):
        variazioni.append(
            f"bordi descritti come \"{c_precedente.get('bordi')}\" in precedenza, ora \"{c_attuale.get('bordi')}\""
        )

    return {
        "variazioni_rilevate": len(variazioni) > 0,
        "descrizione": "; ".join(variazioni) if variazioni else "Nessuna variazione rilevante rispetto alla foto precedente.",
        "avviso_simulazione": AVVISO_SIMULAZIONE,
    }
