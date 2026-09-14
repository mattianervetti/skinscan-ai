"""Pagina Registro di Audit: confronta ciò che il classificatore simulato
aveva ipotizzato con l'esito istologico reale, contando SEPARATAMENTE
concordanza, falso positivo, falso negativo, non conclusivi, e i casi
recuperati da una regola di sicurezza (agenti/followup.py, nucleo/registro_audit.py).

NON mostra MAI una percentuale unica di accuratezza (vedi CLAUDE.md e il
commento in nucleo/registro_audit.py): un falso positivo (biopsia evitabile) e
un falso negativo (melanoma non individuato) hanno un peso clinico molto
diverso — una percentuale unica li mescolerebbe, nascondendo proprio
l'informazione che conta di più."""

import streamlit as st

from nucleo.registro_audit import (
    CATEGORIA_FALSO_NEGATIVO,
    CATEGORIA_FALSO_POSITIVO,
    CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO,
    CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA,
    ETICHETTE_CATEGORIA,
    calcola_riepilogo_audit,
    calcola_riepilogo_supervisione_umana,
)

_DESCRIZIONI_CATEGORIA = {
    CATEGORIA_FALSO_POSITIVO: "Il classificatore diceva sospetta, l'istologico è benigno: una biopsia evitabile.",
    CATEGORIA_FALSO_NEGATIVO: "Il classificatore diceva rassicurante, l'istologico è maligno: un melanoma non individuato dal classificatore.",
    CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA: (
        "Il classificatore diceva rassicurante, ma una regola di sicurezza (neo dichiarato "
        "cambiato, o rischio costituzionale alto) ha comunque mandato il caso al dermatologo, "
        "che ha trovato una lesione maligna: casi che il classificatore da solo avrebbe perso."
    ),
    CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO: "L'esito istologico non è stato conclusivo: non si può dire se il classificatore avesse ragione o torto.",
}


def mostra_pagina() -> None:
    st.title("Registro di Audit")

    st.warning(
        "⚠️ I numeri qui sotto si basano su un classificatore SIMULATO "
        "(nucleo/classificatore.py): non riflettono le prestazioni di un vero "
        "strumento diagnostico. Includono anche ~30 casi storici fittizi, generati "
        "via codice, per mostrare numeri leggibili invece di un solo caso reale."
    )

    riepilogo = calcola_riepilogo_audit()
    conteggi = riepilogo["conteggi"]

    if riepilogo["totale"] == 0:
        st.info("Nessun caso chiuso con un esito istologico ancora.")
        return

    st.write(f"**{riepilogo['totale']} casi chiusi con un esito istologico caricato.**")

    st.caption(
        "Non viene calcolata una percentuale di accuratezza unica: un falso positivo e un "
        "falso negativo hanno un peso clinico molto diverso (una biopsia evitabile contro un "
        "melanoma non individuato) e una percentuale unica li mescolerebbe, nascondendo "
        "proprio l'informazione che conta di più."
    )

    colonne = st.columns(3)
    colonne[0].metric(ETICHETTE_CATEGORIA["concordanza"], conteggi["concordanza"])
    colonne[1].metric(ETICHETTE_CATEGORIA[CATEGORIA_FALSO_POSITIVO], conteggi[CATEGORIA_FALSO_POSITIVO])
    colonne[2].metric(ETICHETTE_CATEGORIA[CATEGORIA_FALSO_NEGATIVO], conteggi[CATEGORIA_FALSO_NEGATIVO])

    st.error(
        f"🔻 **{ETICHETTE_CATEGORIA[CATEGORIA_FALSO_NEGATIVO]}: {conteggi[CATEGORIA_FALSO_NEGATIVO]}** — "
        f"{_DESCRIZIONI_CATEGORIA[CATEGORIA_FALSO_NEGATIVO]}"
    )
    st.warning(
        f"🔺 **{ETICHETTE_CATEGORIA[CATEGORIA_FALSO_POSITIVO]}: {conteggi[CATEGORIA_FALSO_POSITIVO]}** — "
        f"{_DESCRIZIONI_CATEGORIA[CATEGORIA_FALSO_POSITIVO]}"
    )
    st.success(
        f"🛟 **{ETICHETTE_CATEGORIA[CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA]}: "
        f"{conteggi[CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA]}** — "
        f"{_DESCRIZIONI_CATEGORIA[CATEGORIA_RECUPERATO_DA_REGOLA_SICUREZZA]}"
    )

    colonne_2 = st.columns(2)
    colonne_2[0].metric(ETICHETTE_CATEGORIA["non_conclusivi"], conteggi["non_conclusivi"])
    colonne_2[1].metric(
        ETICHETTE_CATEGORIA[CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO], conteggi[CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO]
    )
    if conteggi[CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO] > 0:
        st.caption(_DESCRIZIONI_CATEGORIA[CATEGORIA_ISTOLOGICO_NON_DIAGNOSTICO])

    _mostra_sezione_supervisione_umana()


def _mostra_sezione_supervisione_umana() -> None:
    """Quante volte il dermatologo ha confermato la proposta del sistema per un
    caso in coda, e quante volte l'ha modificata (Fase 3, passo 3). Conteggio
    SEPARATO dal confronto classificatore/istologico sopra: qui si confronta
    la proposta del sistema con la scelta del dermatologo, non l'ipotesi
    dell'algoritmo con l'esito di laboratorio. È l'unica prova che la
    supervisione umana dichiarata dal progetto incida davvero, non sia una
    formalità (vedi nucleo/registro_audit.py)."""
    riepilogo = calcola_riepilogo_supervisione_umana()
    if riepilogo["totale"] == 0:
        return

    st.divider()
    st.subheader("Supervisione umana sulle decisioni")
    st.caption(
        "Quante volte il dermatologo ha confermato la proposta del sistema per un caso in "
        "coda, e quante volte l'ha modificata. Il sistema può proporre di approfondire, mai "
        "di interrompere: chiudere un caso senza accertamenti resta sempre una scelta "
        "esclusiva del dermatologo."
    )
    colonne_supervisione = st.columns(2)
    colonne_supervisione[0].metric("Proposta confermata", riepilogo["conteggi"]["approvato"])
    colonne_supervisione[1].metric("Proposta modificata", riepilogo["conteggi"]["modificato"])
