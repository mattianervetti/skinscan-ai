"""
Regole cliniche di triage per il rischio di melanoma: punto unico di verità,
usato dall'agente ACCOGLIENZA e, in futuro, dagli altri agenti.

Contiene SOLO funzioni pure (nessuna dipendenza da Streamlit, dal database o dal
modello linguistico): possono essere testate isolatamente, senza bisogno di
avviare l'app o contattare Gemini.

ATTENZIONE: questi sono criteri semplificati a scopo dimostrativo, ispirati ai
fattori di rischio riconosciuti per il melanoma (fototipo, numero di nei,
familiarità, precedenti personali, immunosoppressione, età). NON costituiscono
uno strumento clinico validato e non vanno usati per decisioni mediche reali.

Principio del progetto (vedi CLAUDE.md): il modello linguistico non decide MAI
la priorità né il percorso del paziente. Le funzioni di questo file sono le
uniche a farlo, in modo deterministico e testabile.
"""


def calcola_punteggio_rischio_costituzionale(
    *,
    eta: int,
    fototipo: int,
    categoria_nei: str,
    familiarita_melanoma: bool,
    melanoma_pregresso: bool,
    immunosoppressione: bool,
) -> dict:
    """Calcola il punteggio di rischio "costituzionale": i fattori di rischio
    della persona, indipendenti dal sintomo attuale (il neo cambiato si valuta
    a parte, in decidi_percorso).

    Punti assegnati:
    - melanoma pregresso: 5
    - immunosoppressione: 3
    - familiarità di primo grado per melanoma: 2
    - fototipo 1: 2 — fototipo 2: 1 — fototipo 3 o 4: 0
    - più di 50 nei: 2 — da 20 a 50 nei: 1 — meno di 20: 0
    - età superiore a 60 anni: 1

    Soglie: 0-1 = bassa, 2-4 = media, 5 o più = alta.

    Restituisce {"punteggio": int, "priorita": "bassa"/"media"/"alta", "motivo": str}.
    """
    punteggio = 0
    fattori_contati = []

    if melanoma_pregresso:
        punteggio += 5
        fattori_contati.append("melanoma pregresso (+5)")

    if immunosoppressione:
        punteggio += 3
        fattori_contati.append("immunosoppressione (+3)")

    if familiarita_melanoma:
        punteggio += 2
        fattori_contati.append("familiarità di primo grado per melanoma (+2)")

    if fototipo == 1:
        punteggio += 2
        fattori_contati.append("fototipo 1 (+2)")
    elif fototipo == 2:
        punteggio += 1
        fattori_contati.append("fototipo 2 (+1)")
    # Fototipo 3 o 4: 0 punti, nessuna voce aggiunta.

    if categoria_nei == ">50":
        punteggio += 2
        fattori_contati.append("più di 50 nei (+2)")
    elif categoria_nei == "20-50":
        punteggio += 1
        fattori_contati.append("da 20 a 50 nei (+1)")
    elif categoria_nei != "<20":
        raise ValueError(f"categoria_nei non valida: {categoria_nei!r} (attesi '<20', '20-50', '>50')")

    if eta > 60:
        punteggio += 1
        fattori_contati.append("età superiore a 60 anni (+1)")

    if punteggio >= 5:
        priorita = "alta"
    elif punteggio >= 2:
        priorita = "media"
    else:
        priorita = "bassa"

    if fattori_contati:
        elenco_fattori = ", ".join(fattori_contati)
        motivo = f"Fattori di rischio rilevati: {elenco_fattori}. Punteggio totale {punteggio}, rischio {priorita.upper()}."
    else:
        motivo = f"Nessun fattore di rischio costituzionale rilevato. Punteggio totale {punteggio}, rischio {priorita.upper()}."

    return {"punteggio": punteggio, "priorita": priorita, "motivo": motivo}


def decidi_percorso(priorita: str, neo_cambiato: bool) -> dict:
    """Decide il percorso del paziente combinando la priorità costituzionale con
    il sintomo attuale (neo dichiarato cambiato). Il neo cambiato NON entra nel
    punteggio: agisce come interruttore di sicurezza indipendente.

    Matrice:
    - neo cambiato SÌ, qualunque priorità → percorso "foto", sempre al dermatologo
    - neo cambiato NO + priorità alta → percorso "foto", al dermatologo
    - neo cambiato NO + priorità media → percorso "foto", non ancora al dermatologo
    - neo cambiato NO + priorità bassa → percorso "prevenzione", nessun esame

    Restituisce {"percorso": "foto"/"prevenzione", "destinato_dermatologo": bool, "motivo": str}.
    """
    if neo_cambiato:
        return {
            "percorso": "foto",
            "destinato_dermatologo": True,
            "motivo": (
                "Il paziente ha dichiarato che un neo è cambiato: il caso richiede foto "
                "e va comunque al dermatologo, indipendentemente dal punteggio di rischio."
            ),
        }

    if priorita == "alta":
        return {
            "percorso": "foto",
            "destinato_dermatologo": True,
            "motivo": "Nessun sintomo dichiarato, ma il rischio costituzionale è ALTO: il caso richiede foto e va al dermatologo.",
        }

    if priorita == "media":
        return {
            "percorso": "foto",
            "destinato_dermatologo": False,
            "motivo": "Nessun sintomo dichiarato, rischio costituzionale MEDIO: il caso richiede foto per un controllo più approfondito.",
        }

    if priorita == "bassa":
        return {
            "percorso": "prevenzione",
            "destinato_dermatologo": False,
            "motivo": "Nessun sintomo dichiarato, rischio costituzionale BASSO: non è necessario alcun esame, solo consigli di prevenzione.",
        }

    raise ValueError(f"priorita non valida: {priorita!r} (attesi 'bassa', 'media', 'alta')")


GIORNI_CONTROLLO_BREVE = 90
GIORNI_CONTROLLO_MEDIO = 180
GIORNI_CONTROLLO_LUNGO = 365


def decidi_intervallo_controllo(*, priorita: str, classificazione_istologica: str | None) -> dict:
    """Decide fra quanti giorni programmare il prossimo controllo di
    prevenzione, in base all'esito istologico (se c'è stata una biopsia) e
    alla priorità costituzionale del caso.

    Regola (soglie di esempio, facilmente cambiabili):
    - esito istologico maligno → intervallo BREVE, indipendentemente dalla priorità
      (una lesione maligna già trovata richiede un controllo ravvicinato);
    - nessun esito maligno (o nessuna biopsia) e priorità ALTA → intervallo MEDIO;
    - altrimenti (priorità media o bassa) → intervallo LUNGO.

    Restituisce {"giorni": int, "motivo": str}.
    """
    from nucleo.registro_audit import is_istologico_maligno

    if classificazione_istologica is not None and is_istologico_maligno(classificazione_istologica):
        return {
            "giorni": GIORNI_CONTROLLO_BREVE,
            "motivo": f"Esito istologico maligno ({classificazione_istologica.replace('_', ' ')}): controllo ravvicinato.",
        }

    if priorita == "alta":
        return {
            "giorni": GIORNI_CONTROLLO_MEDIO,
            "motivo": "Nessun esito maligno, ma rischio costituzionale ALTO: controllo a intervallo medio.",
        }

    return {
        "giorni": GIORNI_CONTROLLO_LUNGO,
        "motivo": "Nessun esito maligno e rischio costituzionale non alto: controllo di routine a intervallo lungo.",
    }


def decidi_destinazione_dopo_analisi(*, gia_destinato_dermatologo: bool, classificazione: str) -> dict:
    """Applica la regola di sicurezza dell'agente ANALISI: un esito sospetto o
    non conclusivo manda SEMPRE al dermatologo, anche se il caso non lo era già.

    Le altre due regole di sicurezza (neo cambiato, priorità alta) sono già
    state applicate da decidi_percorso all'apertura del caso: qui si rispetta
    quella decisione (gia_destinato_dermatologo) e si aggiunge solo la regola
    legata all'esito del classificatore, senza mai "retrocedere" un caso già
    destinato al dermatologo.

    Restituisce {"destinato_dermatologo": bool, "motivo": str}.
    """
    if gia_destinato_dermatologo:
        return {
            "destinato_dermatologo": True,
            "motivo": "Il caso era già destinato al dermatologo (neo cambiato o priorità alta, decisi dall'agente ACCOGLIENZA).",
        }

    if classificazione in ("sospetta", "non_conclusiva"):
        return {
            "destinato_dermatologo": True,
            "motivo": f"L'esito del classificatore è {classificazione.replace('_', ' ')}: il caso va al dermatologo.",
        }

    return {
        "destinato_dermatologo": False,
        "motivo": "Esito rassicurante e nessun altro fattore di rischio attivo: il caso prosegue con i controlli di routine.",
    }
