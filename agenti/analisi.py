"""
Agente ANALISI: chiama il classificatore simulato sulla foto accettata, la
confronta con lo storico se disponibile, applica le regole di sicurezza e
genera il testo per il paziente.

PRINCIPIO FONDAMENTALE (vedi CLAUDE.md, come per gli agenti precedenti): il
classificatore e il confronto sono SIMULATI (nucleo.classificatore). Le regole
di sicurezza (chi va al dermatologo) sono calcolate SOLO da
nucleo.regole_sicurezza, mai dal modello linguistico. Il modello linguistico
formula solo il testo per il paziente, e NON deve mai comunicare la
classificazione o la confidenza come se fosse una diagnosi: il paziente deve
sapere solo che le immagini sono state elaborate e che la valutazione clinica
spetta al dermatologo.
"""

import json
from datetime import date

from nucleo.classificatore import analizza_lesione, confronta_con_precedente
from nucleo.database import PERCORSO_DATABASE, ottieni_connessione
from nucleo.modello_linguistico import chiedi_al_modello
from nucleo.registro_azioni import registra_azione
from nucleo.regole_sicurezza import decidi_destinazione_dopo_analisi

NOME_AGENTE = "ANALISI"

_CARTELLA_PROGETTO = PERCORSO_DATABASE.parent.parent

_ISTRUZIONE_DI_SISTEMA = (
    "Sei un assistente che comunica a un paziente, in un contesto sanitario, che "
    "le foto inviate di un neo sono state elaborate e qual è il passo successivo. "
    "Segui OBBLIGATORIAMENTE queste regole:\n"
    "1. Registro linguistico formale (terza persona/\"lei\"), professionale ma "
    "comprensibile. Vietati: \"ciao\", punti esclamativi, linguaggio infantilizzante.\n"
    "2. Frasi brevi e verbi attivi (es. \"abbiamo esaminato i dati\", non \"i "
    "dati sono stati esaminati\"). Descrivi SOLO ciò che è indicato più sotto: "
    "non inventare passaggi ulteriori.\n"
    "3. Vietate le formule burocratiche, in qualunque forma, tra cui: \"il "
    "presente caso\", \"si invita pertanto\", \"la relativa valutazione\", \"le "
    "comunicazioni ufficiali\", \"la struttura sanitaria\", \"con successo\".\n"
    "4. Niente perifrasi: scrivi \"le fotografie che ha inviato\", non \"le "
    "immagini fotografiche da lei trasmesse\".\n"
    "5. NON comunicare MAI la classificazione del sistema (es. sospetta, "
    "probabilmente benigna, non conclusiva) né un punteggio di confidenza: il "
    "paziente deve sapere solo che le immagini sono state elaborate, non l'esito "
    "tecnico dell'elaborazione.\n"
    "6. Non rassicurare MAI e non allarmare MAI sull'esito clinico.\n"
    "7. Il genere del paziente non è noto: NON usare MAI forme che richiedano un "
    "accordo di genere riferito al paziente (niente scritture con la barra \"/\").\n"
    "8. Ricorda sempre che ogni valutazione clinica spetta al dermatologo.\n"
    "9. Massimo 5 frasi in tutto.\n"
    "10. Criterio generale: il testo deve suonare come un professionista "
    "sanitario che spiega con chiarezza a una persona, mai come una "
    "comunicazione amministrativa."
)

# Testi di riserva: usati SOLO se la chiamata al modello linguistico fallisce.
# Nessuno dei due rivela mai classificazione o confidenza.
_TESTO_RISERVA_DERMATOLOGO = (
    "Le fotografie che ha inviato sono state elaborate. Abbiamo trasmesso il "
    "caso al dermatologo, che le valuterà insieme al questionario. La "
    "contatteremo non appena avrà completato la valutazione."
)
_TESTO_RISERVA_ROUTINE = (
    "Le fotografie che ha inviato sono state elaborate e il percorso prosegue "
    "con i controlli di routine. Il dermatologo resta comunque il riferimento "
    "per ogni valutazione clinica. Continui con l'autoesame periodico della pelle."
)


def _trova_foto_precedente_diversa(connessione, lesione_id: int, foto_corrente_id: int, impronta_corrente: str) -> dict | None:
    """Cerca, andando a ritroso, la foto accettata più recente della stessa
    lesione con un CONTENUTO diverso da quello corrente (stesso hash = stesso
    file, es. ricaricato due volte in demo/test: non è un confronto significativo,
    si continua a cercare). Restituisce l'esito del classificatore su quella
    foto, o None se non esiste nessuna foto precedente diversa."""
    righe = connessione.execute(
        """SELECT id, percorso_file FROM foto_lesioni
           WHERE lesione_id = ? AND qualita_ok = 1 AND id < ?
           ORDER BY id DESC""",
        (lesione_id, foto_corrente_id),
    ).fetchall()

    for _foto_id, percorso_relativo in righe:
        dati = (_CARTELLA_PROGETTO / percorso_relativo).read_bytes()
        esito = analizza_lesione(dati)
        if esito["impronta_immagine"] != impronta_corrente:
            return esito

    return None


def _genera_testo_e_fonte(domanda: str, destinato_dermatologo: bool) -> tuple[str, str, str | None]:
    try:
        testo, nome_modello = chiedi_al_modello(domanda, istruzione_di_sistema=_ISTRUZIONE_DI_SISTEMA)
        return testo, "modello", nome_modello
    except Exception:
        testo_riserva = _TESTO_RISERVA_DERMATOLOGO if destinato_dermatologo else _TESTO_RISERVA_ROUTINE
        return testo_riserva, "riserva", None


def analizza_caso(caso_id: int) -> dict:
    """Punto di ingresso dell'agente ANALISI per un caso con foto già accettata.

    Chiama il classificatore simulato, confronta con lo storico se disponibile,
    applica la regola di sicurezza sull'esito, salva tutto nel database
    (con l'avviso di simulazione nella stessa riga del dato, come richiesto per
    la futura scheda del dermatologo) e genera il testo per il paziente.
    """
    connessione = ottieni_connessione()
    try:
        riga_caso = connessione.execute(
            "SELECT lesione_id, stato FROM casi WHERE id = ?", (caso_id,)
        ).fetchone()
        if riga_caso is None:
            raise ValueError(f"Nessun caso trovato con id {caso_id}")
        lesione_id, stato_attuale = riga_caso
        if lesione_id is None:
            raise ValueError(f"Il caso {caso_id} non ha ancora nessuna foto accettata associata.")

        riga_foto = connessione.execute(
            """SELECT id, percorso_file FROM foto_lesioni
               WHERE lesione_id = ? AND qualita_ok = 1 ORDER BY id DESC LIMIT 1""",
            (lesione_id,),
        ).fetchone()
        if riga_foto is None:
            raise ValueError(f"Nessuna foto accettata trovata per il caso {caso_id}.")
        foto_id, percorso_relativo = riga_foto

        dati_foto_corrente = (_CARTELLA_PROGETTO / percorso_relativo).read_bytes()

        # --- Classificazione: SOLO il modulo simulato, mai il modello linguistico. ---
        esito = analizza_lesione(dati_foto_corrente)

        esito_precedente = _trova_foto_precedente_diversa(connessione, lesione_id, foto_id, esito["impronta_immagine"])
        if esito_precedente is not None:
            confronto = confronta_con_precedente(esito, esito_precedente)
        else:
            confronto = None

        # --- Regola di sicurezza: SOLO codice, mai il modello linguistico. ---
        gia_destinato_dermatologo = stato_attuale == "in_coda_dermatologo"
        decisione = decidi_destinazione_dopo_analisi(
            gia_destinato_dermatologo=gia_destinato_dermatologo,
            classificazione=esito["classificazione"],
        )
        destinato_dermatologo = decisione["destinato_dermatologo"]

        # --- Salvataggio: avviene PRIMA di contattare il modello linguistico. ---
        oggi = date.today().isoformat()
        connessione.execute(
            """INSERT INTO analisi_classificatore
               (foto_id, esito, confidenza, caratteristiche, confronto_storico, avviso_simulazione, data_analisi)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                foto_id,
                esito["classificazione"],
                esito["confidenza"],
                json.dumps(esito["caratteristiche"], ensure_ascii=False),
                confronto["descrizione"] if confronto else None,
                esito["avviso_simulazione"],
                oggi,
            ),
        )

        nuovo_stato = "in_coda_dermatologo" if destinato_dermatologo else "analisi_rassicurante"
        connessione.execute("UPDATE casi SET stato = ? WHERE id = ?", (nuovo_stato, caso_id))
        connessione.commit()
    finally:
        connessione.close()

    # --- Testo per il paziente: SOLO qui entra il modello linguistico. ---
    domanda = (
        "Le foto del paziente sono state elaborate. "
        f"{'Il caso è destinato al dermatologo.' if destinato_dermatologo else 'Il caso prosegue con i controlli di routine, senza priorità aggiuntiva verso il dermatologo in questo momento.'} "
        "Scrivi il messaggio per il paziente seguendo esattamente la struttura e le "
        "regole indicate nelle istruzioni di sistema."
    )
    testo_paziente, fonte_testo, modello_usato = _genera_testo_e_fonte(domanda, destinato_dermatologo)

    # --- Registro: sempre scritto, con quale regola di sicurezza è scattata. ---
    input_dati = (
        f"Foto id {foto_id} — classificazione: {esito['classificazione']}, confidenza: {esito['confidenza']}"
        + (f" — confronto: {confronto['descrizione']}" if confronto else " — nessuna foto precedente per il confronto")
    )
    decisione_testo = (
        "Caso inoltrato al dermatologo" if destinato_dermatologo else "Caso in controlli di routine, non inoltrato al dermatologo"
    )
    motivo_registro = decisione["motivo"]
    if fonte_testo == "modello":
        motivo_registro += f" [Testo per il paziente generato dal modello {modello_usato}.]"
    else:
        motivo_registro += " [Testo per il paziente generato con contenuto di riserva: modello linguistico non disponibile.]"

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=input_dati,
        decisione=decisione_testo,
        motivo=motivo_registro,
        caso_id=caso_id,
    )

    return {
        "caso_id": caso_id,
        "classificazione": esito["classificazione"],
        "confidenza": esito["confidenza"],
        "caratteristiche": esito["caratteristiche"],
        "avviso_simulazione": esito["avviso_simulazione"],
        "confronto": confronto,
        "destinato_dermatologo": destinato_dermatologo,
        "stato": "in_coda_dermatologo" if destinato_dermatologo else "analisi_rassicurante",
        "testo_paziente": testo_paziente,
        "fonte_testo": fonte_testo,
        "modello_usato": modello_usato,
    }
