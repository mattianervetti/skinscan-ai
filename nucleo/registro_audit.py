"""
Registro di audit: confronta ciò che il classificatore simulato aveva
ipotizzato con ciò che l'esito istologico ha poi rivelato davvero, e conta
quante volte ciascuna cosa è successa. Usato dall'agente FOLLOW-UP quando
carica un esito istologico, e dalla pagina "Registro di Audit".

PRINCIPIO (vedi CLAUDE.md): NON si calcola una percentuale di accuratezza
complessiva. I due tipi di errore hanno un peso clinico diverso: un falso
positivo (l'algoritmo diceva sospetta, l'istologico è benigno) comporta una
biopsia evitabile; un falso negativo (l'algoritmo diceva rassicurante,
l'istologico è maligno) comporta un melanoma non individuato. Una percentuale
unica di accuratezza mescolerebbe i due casi e nasconderebbe proprio
l'informazione che conta di più. Per questo si contano SEPARATAMENTE:
concordanza, falso positivo, falso negativo, non conclusivi (l'algoritmo non
si era espresso), e — categoria a parte, mai confusa con un falso negativo —
i casi in cui una regola di sicurezza (neo dichiarato cambiato, o rischio
costituzionale alto) ha comunque mandato il caso dal dermatologo nonostante
un esito rassicurante del classificatore: sono i casi che il classificatore
da solo avrebbe perso, e che le regole hanno recuperato.

categorizza_confronto() è una funzione PURA (nessuna dipendenza dal database):
testabile da sola, e usata identica sia per i casi reali sia per i casi
storici fittizi generati in nucleo/dati_demo.py, così le due fonti di dati
non possono mai essere classificate con logiche diverse.
"""

from nucleo.database import ottieni_connessione

# Le 5 scelte predefinite tra cui il dermatologo sceglie quando carica un esito
# istologico (pages/dermatologo.py): vocabolario fisso, non testo libero, perché
# il registro di audit deve poter distinguere benigno da maligno in modo affidabile.
CLASSIFICAZIONI_ISTOLOGICHE_POSSIBILI = (
    "benigno",
    "melanoma_in_situ",
    "melanoma_invasivo",
    "altra_lesione_maligna",
    "non_diagnostico",
)

ETICHETTE_ISTOLOGICO = {
    "benigno": "Benigno",
    "melanoma_in_situ": "Melanoma in situ",
    "melanoma_invasivo": "Melanoma invasivo",
    "altra_lesione_maligna": "Altra lesione maligna",
    "non_diagnostico": "Non diagnostico",
}

# Le classificazioni istologiche che confermano una lesione maligna. Le altre
# due (benigno, non_diagnostico) non lo sono — non_diagnostico è comunque
# gestito a parte in categorizza_confronto: senza un esito chiaro non si può
# dire se il classificatore avesse ragione o torto.
_ISTOLOGICI_MALIGNI = frozenset({"melanoma_in_situ", "melanoma_invasivo", "altra_lesione_maligna"})

CATEGORIA_CONCORDANZA = "concordanza"
CATEGORIA_FALSO_POSITIVO = "falso_positivo"
CATEGORIA_FALSO_NEGATIVO = "falso_negativo"
CATEGORIA_NON_CONCLUSIVI = "non_conclusivi"
CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA = "recuperato_da_regola_sicurezza"
CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO = "istologico_non_diagnostico"

_TUTTE_LE_CATEGORIE = (
    CATEGORIA_CONCORDANZA,
    CATEGORIA_FALSO_POSITIVO,
    CATEGORIA_FALSO_NEGATIVO,
    CATEGORIA_NON_CONCLUSIVI,
    CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA,
    CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO,
)

ETICHETTE_CATEGORIA = {
    CATEGORIA_CONCORDANZA: "Concordanza",
    CATEGORIA_FALSO_POSITIVO: "Falso positivo",
    CATEGORIA_FALSO_NEGATIVO: "Falso negativo",
    CATEGORIA_NON_CONCLUSIVI: "Non conclusivi",
    CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA: "Recuperati da una regola di sicurezza",
    CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO: "Istologico non diagnostico",
}


def is_istologico_maligno(classificazione_istologica: str) -> bool:
    """Vero se la classificazione istologica conferma una lesione maligna."""
    return classificazione_istologica in _ISTOLOGICI_MALIGNI


def categorizza_confronto(
    *,
    classificazione_algoritmo: str,
    classificazione_istologica: str,
    gia_destinato_indipendentemente_dal_classificatore: bool,
) -> str:
    """Confronta l'ipotesi del classificatore simulato (classificazione_algoritmo:
    'sospetta', 'probabilmente_benigna' o 'non_conclusiva') con l'esito istologico
    reale, e restituisce UNA delle costanti CATEGORIA_*.

    gia_destinato_indipendentemente_dal_classificatore: vero se il caso sarebbe
    comunque arrivato al dermatologo per una regola di sicurezza (neo dichiarato
    cambiato, o rischio costituzionale alto) indipendentemente da cosa avesse
    detto il classificatore — si ricostruisce da questionari.neo_cambiato e
    casi.priorita, esattamente la stessa condizione già usata in
    nucleo.regole_sicurezza.decidi_percorso, senza bisogno di salvarla di nuovo.
    """
    if classificazione_istologica == "non_diagnostico":
        return CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO

    istologico_maligno = is_istologico_maligno(classificazione_istologica)

    if classificazione_algoritmo == "non_conclusiva":
        return CATEGORIA_NON_CONCLUSIVI

    if classificazione_algoritmo == "sospetta":
        return CATEGORIA_CONCORDANZA if istologico_maligno else CATEGORIA_FALSO_POSITIVO

    if classificazione_algoritmo == "probabilmente_benigna":
        if not istologico_maligno:
            return CATEGORIA_CONCORDANZA
        if gia_destinato_indipendentemente_dal_classificatore:
            return CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA
        return CATEGORIA_FALSO_NEGATIVO

    raise ValueError(f"classificazione_algoritmo non valida: {classificazione_algoritmo!r}")


def calcola_riepilogo_audit() -> dict:
    """Legge tutti i casi con un esito istologico caricato (reali e storici: per
    questa funzione sono indistinguibili) e restituisce i conteggi per categoria.

    Restituisce {"conteggi": {categoria: numero}, "totale": int}.
    """
    connessione = ottieni_connessione()
    try:
        righe = connessione.execute("SELECT categoria_confronto FROM esiti_istologici").fetchall()
    finally:
        connessione.close()

    conteggi = {categoria: 0 for categoria in _TUTTE_LE_CATEGORIE}
    for (categoria,) in righe:
        conteggi[categoria] += 1

    return {"conteggi": conteggi, "totale": len(righe)}


def calcola_riepilogo_supervisione_umana() -> dict:
    """Conta quante decisioni del dermatologo su un caso in coda (Fase 3,
    passo 3: agenti/decisione_dermatologo.py) hanno confermato la proposta del
    sistema ('approvato') e quante l'hanno modificata ('modificato').

    Questo è un audit DIVERSO da calcola_riepilogo_audit() sopra (quello
    confronta il classificatore simulato con l'esito istologico): qui si
    confronta la proposta del sistema con la scelta del dermatologo. Il numero
    di volte in cui il dermatologo corregge il sistema è l'unica prova che la
    supervisione umana dichiarata dal progetto incida davvero sulle decisioni,
    non sia una formalità — un sistema che si limitasse a osservare quante
    volte viene "approvato" senza mai contare le modifiche non potrebbe
    dimostrarlo.

    Restituisce {"conteggi": {"approvato": int, "modificato": int}, "totale": int}.
    """
    connessione = ottieni_connessione()
    try:
        righe = connessione.execute("SELECT decisione FROM decisioni_dermatologo").fetchall()
    finally:
        connessione.close()

    conteggi = {"approvato": 0, "modificato": 0}
    for (decisione,) in righe:
        conteggi[decisione] += 1

    return {"conteggi": conteggi, "totale": len(righe)}
