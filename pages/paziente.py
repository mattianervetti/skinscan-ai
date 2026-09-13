"""Pagina Paziente: questionario di valutazione del rischio e visualizzazione
dell'esito prodotto dall'agente ACCOGLIENZA."""

import streamlit as st

from agenti.accoglienza import rigenera_testo_paziente, valuta_questionario
from agenti.analisi import analizza_caso
from agenti.guida_foto import ISTRUZIONI_PRE_SCATTO, TENTATIVI_MASSIMI, conta_tentativi, valuta_foto
from agenti.instradamento import conferma_appuntamento, instrada_caso, ottieni_stato_instradamento, sollecita_appuntamento
from nucleo.database import crea_paziente_con_questionario, ottieni_connessione

_STATO_AVANZAMENTO_LEGGIBILE = {
    "in_coda_dermatologo": "Il caso è stato inoltrato al dermatologo per la valutazione.",
    "analisi_rassicurante": "Il caso prosegue con i controlli di routine.",
}

_NOMI_PAZIENTI_DEMO = ["Marta", "Luca", "Paolo", "Giulia"]

_DESCRIZIONI_FOTOTIPO = {
    1: "Fototipo 1 — pelle molto chiara, si scotta sempre, non si abbronza mai",
    2: "Fototipo 2 — pelle chiara, si scotta facilmente, si abbronza poco",
    3: "Fototipo 3 — pelle olivastra, si scotta a volte, si abbronza gradualmente",
    4: "Fototipo 4 — pelle scura, si scotta raramente, si abbronza facilmente",
}

_ETICHETTE_NEI = {"<20": "Meno di 20", "20-50": "Tra 20 e 50", ">50": "Più di 50"}


def _elenca_pazienti_demo() -> list[tuple[int, str]]:
    connessione = ottieni_connessione()
    try:
        segnaposto = ",".join("?" * len(_NOMI_PAZIENTI_DEMO))
        righe = connessione.execute(
            f"SELECT id, nome FROM pazienti WHERE nome IN ({segnaposto}) ORDER BY id",
            _NOMI_PAZIENTI_DEMO,
        ).fetchall()
    finally:
        connessione.close()
    return righe


def _leggi_questionario(paziente_id: int) -> dict | None:
    connessione = ottieni_connessione()
    try:
        riga_paziente = connessione.execute(
            "SELECT nome, eta FROM pazienti WHERE id = ?", (paziente_id,)
        ).fetchone()
        riga_questionario = connessione.execute(
            """SELECT fototipo, categoria_nei, familiarita_melanoma, melanoma_pregresso,
                      immunosoppressione, neo_cambiato
               FROM questionari WHERE paziente_id = ? ORDER BY id DESC LIMIT 1""",
            (paziente_id,),
        ).fetchone()
    finally:
        connessione.close()

    if riga_paziente is None or riga_questionario is None:
        return None

    nome, eta = riga_paziente
    fototipo, categoria_nei, familiarita, melanoma_pregresso, immunosoppressione, neo_cambiato = riga_questionario
    return {
        "nome": nome,
        "eta": eta,
        "fototipo": fototipo,
        "categoria_nei": categoria_nei,
        "familiarita_melanoma": bool(familiarita),
        "melanoma_pregresso": bool(melanoma_pregresso),
        "immunosoppressione": bool(immunosoppressione),
        "neo_cambiato": bool(neo_cambiato),
    }


def _mostra_questionario_sola_lettura(dati: dict) -> None:
    st.write(f"**{dati['nome']}**, {dati['eta']} anni")
    st.write(f"- {_DESCRIZIONI_FOTOTIPO[dati['fototipo']]}")
    st.write(f"- Numero di nei: {_ETICHETTE_NEI[dati['categoria_nei']]}")
    st.write(f"- Familiarità di primo grado per melanoma: {'Sì' if dati['familiarita_melanoma'] else 'No'}")
    st.write(f"- Melanoma pregresso: {'Sì' if dati['melanoma_pregresso'] else 'No'}")
    st.write(f"- Immunosoppressione: {'Sì' if dati['immunosoppressione'] else 'No'}")
    st.write(f"- Neo dichiarato cambiato di recente: {'Sì' if dati['neo_cambiato'] else 'No'}")


def _mostra_esito(esito: dict) -> None:
    st.subheader("Esito")

    mostra_priorita = {"bassa": st.success, "media": st.warning, "alta": st.error}[esito["priorita"]]
    mostra_priorita(f"Priorità calcolata: {esito['priorita'].upper()} (punteggio {esito['punteggio']})")

    if esito["percorso"] == "prevenzione":
        st.write("**Cosa succede ora:** nessun esame necessario, solo consigli di prevenzione.")
    else:
        cosa_succede = "verranno richieste le foto guidate dei nei"
        if esito["destinato_dermatologo"]:
            cosa_succede += ", e il caso sarà valutato da un dermatologo"
        st.write(f"**Cosa succede ora:** {cosa_succede}.")

    st.write("**Messaggio per il paziente:**")
    st.write(esito["testo_paziente"])

    if esito["fonte_testo"] == "riserva":
        st.caption(
            "ℹ️ Questo testo è stato generato con un contenuto di riserva: il modello "
            "linguistico non era raggiungibile in questo momento. La priorità e il "
            "percorso assegnati non sono comunque influenzati da questo."
        )


def _mostra_esito_foto(risultato: dict) -> None:
    st.write(
        f"Nitidezza: {risultato['nitidezza']:.1f} — "
        f"Luminosità: {risultato['luminosita']:.1f} — "
        f"Risoluzione: {risultato['larghezza']}×{risultato['altezza']}"
    )

    if risultato["qualita_insufficiente_forzata"]:
        st.warning(f"⚠️ {risultato['testo_paziente']}")
    elif risultato["accettata"]:
        st.success(f"✅ {risultato['testo_paziente']}")
    else:
        st.error(f"❌ Foto non utilizzabile (tentativo {risultato['tentativo_numero']}/{risultato['tentativi_massimi']})")
        st.write(risultato["testo_paziente"])

    if risultato["fonte_testo"] == "riserva" and not risultato["accettata"] and not risultato["qualita_insufficiente_forzata"]:
        st.caption(
            "ℹ️ Messaggio generato con contenuto di riserva: il modello linguistico "
            "non era raggiungibile in questo momento."
        )


def _mostra_esito_analisi(esito_analisi: dict) -> None:
    st.subheader("Stato di avanzamento")
    st.write(_STATO_AVANZAMENTO_LEGGIBILE[esito_analisi["stato"]])
    st.write(esito_analisi["testo_paziente"])

    if esito_analisi["fonte_testo"] == "riserva":
        st.caption(
            "ℹ️ Messaggio generato con contenuto di riserva: il modello linguistico "
            "non era raggiungibile in questo momento."
        )


def _mostra_sezione_instradamento(caso_id: int) -> None:
    info = ottieni_stato_instradamento(caso_id)
    if info is None:
        return

    st.subheader("Televisita")

    if info["stato_appuntamento"] == "confermato":
        st.success(f"Televisita confermata per il {info['data_ora']}.")
    elif info["stato_appuntamento"] == "scalato_operatore":
        st.warning(
            "Non abbiamo ricevuto conferma dopo i solleciti: un operatore la contatterà "
            "direttamente per fissare la televisita."
        )
    else:
        st.write(f"Proposta di televisita per il {info['data_ora']}.")
        if info["numero_solleciti"] > 0:
            st.caption(f"Solleciti inviati finora: {info['numero_solleciti']}.")

        colonna_conferma, colonna_simula = st.columns(2)
        with colonna_conferma:
            if st.button("✅ Conferma disponibilità", key=f"conferma_{caso_id}"):
                conferma_appuntamento(info["appuntamento_id"])
                st.rerun()
        with colonna_simula:
            if st.button(
                "⏱️ Simula: nessuna risposta (demo)",
                key=f"sollecito_{caso_id}",
                help=(
                    "Solo per la demo: simula il passare del tempo senza conferma del "
                    "paziente, per mostrare i solleciti e l'eventuale scalo a un operatore."
                ),
            ):
                sollecita_appuntamento(info["appuntamento_id"])
                st.rerun()


def _mostra_sezione_foto(caso_id: int) -> None:
    st.subheader("Acquisizione foto")

    esiti_foto = st.session_state.setdefault("esiti_foto", {})
    ultimo_risultato = esiti_foto.get(caso_id)

    if ultimo_risultato is not None:
        _mostra_esito_foto(ultimo_risultato)
        if ultimo_risultato["accettata"]:
            esiti_analisi = st.session_state.setdefault("esiti_analisi", {})
            esito_analisi = esiti_analisi.get(caso_id)
            if esito_analisi is not None:
                st.divider()
                _mostra_esito_analisi(esito_analisi)
                if esito_analisi["destinato_dermatologo"]:
                    st.divider()
                    _mostra_sezione_instradamento(caso_id)
            return
        st.divider()

    st.markdown(ISTRUZIONI_PRE_SCATTO)

    tentativo_prossimo = conta_tentativi(caso_id) + 1
    st.caption(f"Tentativo {tentativo_prossimo} di {TENTATIVI_MASSIMI}")

    modalita_foto = st.radio(
        "Come vuoi fornire la foto?",
        ["Fotocamera", "Carica un file"],
        horizontal=True,
        key=f"modalita_foto_{caso_id}_{tentativo_prossimo}",
    )

    dati_immagine = None
    if modalita_foto == "Fotocamera":
        scatto = st.camera_input("Scatta la foto", key=f"camera_{caso_id}_{tentativo_prossimo}")
        if scatto is not None:
            dati_immagine = scatto.getvalue()
    else:
        file_caricato = st.file_uploader(
            "Carica un'immagine (utile in demo: usa i file in data/demo/immagini)",
            type=["png", "jpg", "jpeg"],
            key=f"upload_{caso_id}_{tentativo_prossimo}",
        )
        if file_caricato is not None:
            dati_immagine = file_caricato.getvalue()

    if dati_immagine is not None:
        st.image(dati_immagine, caption="Foto ricevuta", width=250)
        if st.button("Invia foto", key=f"invia_{caso_id}_{tentativo_prossimo}"):
            with st.spinner("Verifica qualità in corso..."):
                risultato = valuta_foto(caso_id, dati_immagine)
            esiti_foto[caso_id] = risultato

            if risultato["accettata"]:
                with st.spinner("Elaborazione delle immagini in corso..."):
                    esito_analisi = analizza_caso(caso_id)
                st.session_state.setdefault("esiti_analisi", {})[caso_id] = esito_analisi
                if esito_analisi["destinato_dermatologo"]:
                    instrada_caso(caso_id)

            st.rerun()


def mostra_pagina() -> None:
    st.title("Area Paziente")

    modalita = st.radio(
        "Cosa vuoi fare?",
        ["Rivedi un paziente demo", "Compila un nuovo questionario"],
        horizontal=True,
    )

    if modalita == "Rivedi un paziente demo":
        pazienti_demo = _elenca_pazienti_demo()
        if not pazienti_demo:
            st.warning("Nessun paziente demo trovato nel database. Prova a reimpostare la demo dalla barra laterale.")
            return

        etichette = [nome for _id, nome in pazienti_demo]
        scelta = st.selectbox("Scegli un paziente demo", etichette)
        paziente_id = next(id_ for id_, nome in pazienti_demo if nome == scelta)

        dati_questionario = _leggi_questionario(paziente_id)
        if dati_questionario is None:
            st.error("Questionario non trovato per questo paziente.")
            return

        st.subheader("Questionario già compilato")
        _mostra_questionario_sola_lettura(dati_questionario)

        colonna_esito, colonna_rigenera = st.columns([3, 2])
        with colonna_esito:
            if st.button("Ottieni esito"):
                with st.spinner("Valutazione in corso..."):
                    esito = valuta_questionario(paziente_id)
                st.session_state["ultimo_esito"] = esito
        with colonna_rigenera:
            if st.button("🔄 Rigenera testo (sviluppo)", help="Sovrascrive il testo salvato per l'ultimo caso di questo paziente, senza cambiare priorità o percorso. Utile per verificare le istruzioni date al modello linguistico."):
                try:
                    with st.spinner("Rigenerazione in corso..."):
                        esito = rigenera_testo_paziente(paziente_id)
                    st.session_state["ultimo_esito"] = esito
                except ValueError as errore:
                    st.error(str(errore))

    else:
        st.subheader("Nuovo questionario")
        with st.form("form_nuovo_questionario"):
            nome = st.text_input("Nome")
            eta = st.number_input("Età", min_value=0, max_value=120, value=40)
            fototipo = st.selectbox(
                "Che tipo di pelle hai?",
                options=[1, 2, 3, 4],
                format_func=lambda valore: _DESCRIZIONI_FOTOTIPO[valore],
            )
            categoria_nei = st.radio(
                "Quanti nei hai, all'incirca?",
                options=["<20", "20-50", ">50"],
                format_func=lambda valore: _ETICHETTE_NEI[valore],
            )
            familiarita_melanoma = st.radio(
                "Un tuo familiare di primo grado (genitore, fratello/sorella, figlio/a) ha mai avuto un melanoma?",
                options=["No", "Sì"],
            ) == "Sì"
            melanoma_pregresso = st.radio(
                "Hai già avuto in passato un melanoma?",
                options=["No", "Sì"],
            ) == "Sì"
            immunosoppressione = st.radio(
                "Segui una terapia che riduce le difese immunitarie, o hai una condizione di immunosoppressione?",
                options=["No", "Sì"],
            ) == "Sì"
            neo_cambiato = st.radio(
                "Hai notato un neo che è cambiato di recente (forma, colore o dimensione)?",
                options=["No", "Sì"],
            ) == "Sì"

            inviato = st.form_submit_button("Invia questionario e ottieni esito")

        if inviato:
            if not nome.strip():
                st.error("Inserisci un nome prima di procedere.")
                return

            paziente_id = crea_paziente_con_questionario(
                nome=nome.strip(),
                eta=int(eta),
                fototipo=fototipo,
                categoria_nei=categoria_nei,
                familiarita_melanoma=familiarita_melanoma,
                melanoma_pregresso=melanoma_pregresso,
                immunosoppressione=immunosoppressione,
                neo_cambiato=neo_cambiato,
            )
            with st.spinner("Valutazione in corso..."):
                esito = valuta_questionario(paziente_id)
            st.session_state["ultimo_esito"] = esito

    if "ultimo_esito" in st.session_state:
        st.divider()
        esito = st.session_state["ultimo_esito"]
        _mostra_esito(esito)

        if esito["percorso"] == "foto":
            st.divider()
            _mostra_sezione_foto(esito["caso_id"])
