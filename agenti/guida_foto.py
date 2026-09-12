"""
Agente GUIDA ALLA FOTO: guida il paziente nello scatto e valuta la qualità
delle foto ricevute.

PRINCIPIO FONDAMENTALE (vedi CLAUDE.md, come per l'Agente ACCOGLIENZA): la
qualità dell'immagine è misurata SOLO da nucleo.qualita_immagine (OpenCV, soglie
numeriche esplicite). Il modello linguistico non giudica mai la qualità di una
foto: viene usato SOLO per formulare il messaggio di correzione da mostrare al
paziente, dopo che la decisione (accettata/rifiutata, e per quale motivo) è già
stata presa dal codice.

Questo file contiene funzioni Python normali, senza dipendenze dall'interfaccia
(Streamlit): in Fase 3 diventerà un nodo di un grafo LangGraph, ma per ora resta
richiamabile e testabile direttamente.
"""

from datetime import date

from nucleo.database import PERCORSO_DATABASE, ottieni_connessione
from nucleo.modello_linguistico import chiedi_al_modello
from nucleo.qualita_immagine import valuta_qualita
from nucleo.registro_azioni import registra_azione

NOME_AGENTE = "GUIDA ALLA FOTO"

# Dopo questo numero di tentativi falliti, la foto viene accettata comunque
# (vedi il commento sulla "regola di non esclusione" dentro valuta_foto per il motivo).
TENTATIVI_MASSIMI = 3


ISTRUZIONI_PRE_SCATTO = (
    "Prima di scattare la foto:\n"
    "- Tenga il telefono a circa 15-20 centimetri dalla pelle, in modo che il neo "
    "riempia buona parte dell'immagine senza essere troppo vicino da risultare sfocato.\n"
    "- Scatti in un ambiente ben illuminato, preferibilmente con luce naturale, "
    "evitando ombre forti dirette sulla zona.\n"
    "- Mantenga il telefono fermo e la messa a fuoco stabile prima di scattare.\n"
    "- Inquadri il neo al centro della foto, ben visibile e non tagliato ai bordi.\n"
    "- Se il neo si trova in una zona che non riesce a vedere o raggiungere "
    "facilmente da solo (ad esempio schiena o nuca), si faccia aiutare da un'altra "
    "persona per lo scatto."
)


_ISTRUZIONE_DI_SISTEMA_CORREZIONE = (
    "Sei un assistente che spiega a un paziente, in un contesto sanitario, perché "
    "una foto appena scattata di un neo non è utilizzabile e cosa deve correggere "
    "per rifarla. Segui OBBLIGATORIAMENTE queste regole:\n"
    "1. Registro linguistico formale (terza persona/\"lei\"), professionale ma "
    "comprensibile. Vietati: \"ciao\", punti esclamativi, linguaggio infantilizzante.\n"
    "2. Il genere del paziente non è noto: NON usare MAI aggettivi, participi o "
    "altre parole che richiedano un accordo di genere riferito al paziente (vietate "
    "forme come \"pronto/a\" o scritture con la barra \"/\"). Riformula sempre in modo neutro.\n"
    "3. Spiega in modo specifico e pratico SOLO il problema tecnico indicato (non "
    "inventare altri difetti) e cosa fare per correggerlo al prossimo scatto.\n"
    "4. Non parlare di diagnosi o rischio clinico: qui si parla solo della qualità "
    "tecnica della foto.\n"
    "5. Massimo 4 frasi in tutto."
)

# Testi di riserva, uno per problema: usati SOLO se la chiamata al modello
# linguistico fallisce per qualsiasi motivo. La decisione (accettata/rifiutata)
# è già presa dal codice indipendentemente da questo testo.
_TESTI_RISERVA_PER_PROBLEMA = {
    "mossa": (
        "La foto risulta mossa o fuori fuoco e non permette di distinguere bene i "
        "dettagli del neo. Tenga il telefono fermo con entrambe le mani, attenda che "
        "la messa a fuoco si stabilizzi prima di scattare, ed eviti di scattare in "
        "movimento. Provi a rifare la foto."
    ),
    "troppo_scura": (
        "La foto risulta troppo scura per poter valutare bene il neo. Si sposti in "
        "un ambiente con più luce, preferibilmente naturale, evitando di scattare in "
        "controluce o con l'ombra del telefono sulla zona. Provi a rifare la foto."
    ),
    "troppo_chiara": (
        "La foto risulta troppo chiara, con dettagli persi per l'eccesso di luce. "
        "Eviti la luce diretta e intensa (ad esempio il sole a mezzogiorno o un "
        "flash molto vicino) e provi a scattare con una luce più uniforme. Provi a "
        "rifare la foto."
    ),
    "risoluzione_bassa": (
        "La foto ha una risoluzione troppo bassa per essere utile: i dettagli del "
        "neo non sono abbastanza definiti. Verifichi le impostazioni della fotocamera "
        "e si assicuri di non aver inviato un'immagine ridotta o compressa. Provi a "
        "rifare la foto."
    ),
}

_MESSAGGIO_ACCETTATA = (
    "Foto ricevuta e utilizzabile. Il caso procede al passo successivo."
)

_MESSAGGIO_ACCETTATA_QUALITA_INSUFFICIENTE = (
    "Dopo diversi tentativi la foto continua a non raggiungere gli standard di "
    "qualità richiesti. Per non ritardare la presa in carico, il caso procede "
    "comunque: la foto verrà valutata dal dermatologo, con l'indicazione che la "
    "qualità dell'immagine è insufficiente."
)


def _conta_tentativi_precedenti(connessione, caso_id: int) -> int:
    riga = connessione.execute(
        "SELECT COUNT(*) FROM log_agenti WHERE caso_id = ? AND agente = ?",
        (caso_id, NOME_AGENTE),
    ).fetchone()
    return riga[0]


def _trova_o_crea_lesione(connessione, paziente_id: int) -> int:
    riga = connessione.execute(
        "SELECT id FROM lesioni WHERE paziente_id = ? ORDER BY id DESC LIMIT 1",
        (paziente_id,),
    ).fetchone()
    if riga is not None:
        return riga[0]

    oggi = date.today().isoformat()
    cursore = connessione.execute(
        "INSERT INTO lesioni (paziente_id, etichetta, data_creazione) VALUES (?, ?, ?)",
        (paziente_id, "Lesione monitorata", oggi),
    )
    return cursore.lastrowid


def _genera_messaggio_correzione(problema: str) -> tuple[str, str, str | None]:
    """Genera il messaggio di correzione per il paziente. Restituisce
    (testo, fonte_testo, nome_modello_usato)."""
    domanda = (
        f"La foto del paziente è stata rifiutata per il seguente problema tecnico: "
        f"{problema}. Spiega cosa correggere, seguendo esattamente le regole delle "
        f"istruzioni di sistema."
    )
    try:
        testo, nome_modello = chiedi_al_modello(domanda, istruzione_di_sistema=_ISTRUZIONE_DI_SISTEMA_CORREZIONE)
        return testo, "modello", nome_modello
    except Exception:
        return _TESTI_RISERVA_PER_PROBLEMA[problema], "riserva", None


def conta_tentativi(caso_id: int) -> int:
    """Numero di tentativi di scatto già registrati per questo caso. Funzione
    pubblica per l'interfaccia (es. per mostrare "tentativo N di 3" e per dare
    una chiave univoca ai widget di caricamento a ogni nuovo tentativo)."""
    connessione = ottieni_connessione()
    try:
        return _conta_tentativi_precedenti(connessione, caso_id)
    finally:
        connessione.close()


def valuta_foto(caso_id: int, dati_immagine: bytes) -> dict:
    """Punto di ingresso dell'agente GUIDA ALLA FOTO per un tentativo di scatto.

    Misura la qualità (OpenCV, soglie numeriche), decide se accettare o
    rifare/accettare-comunque, salva sempre il file e la riga in foto_lesioni,
    genera il messaggio per il paziente (dal modello se serve rifare, testo
    fisso se accettata) e registra sempre l'azione nel registro.
    """
    connessione = ottieni_connessione()
    try:
        riga_caso = connessione.execute(
            "SELECT paziente_id, lesione_id FROM casi WHERE id = ?", (caso_id,)
        ).fetchone()
        if riga_caso is None:
            raise ValueError(f"Nessun caso trovato con id {caso_id}")
        paziente_id, lesione_id = riga_caso

        tentativo_numero = _conta_tentativi_precedenti(connessione, caso_id) + 1

        # --- Misura: SOLO codice/OpenCV, mai il modello linguistico. ---
        esito_qualita = valuta_qualita(dati_immagine)

        # --- Regola di non esclusione, scritta nel codice (non affidata al
        # modello linguistico): dopo TENTATIVI_MASSIMI tentativi falliti, il
        # sistema accetta comunque l'ultima immagine invece di bloccare il
        # paziente. Bloccare il percorso escluderebbe dalla prevenzione chi ha
        # meno dimestichezza con la tecnologia, difficoltà visive, o un neo in
        # una posizione difficile da fotografare — spesso proprio le persone più
        # anziane e più a rischio. La qualità insufficiente deve essere
        # un'informazione per il dermatologo, non un ostacolo per il paziente. ---
        qualita_insufficiente_forzata = (
            not esito_qualita["utilizzabile"] and tentativo_numero >= TENTATIVI_MASSIMI
        )
        accettata = esito_qualita["utilizzabile"] or qualita_insufficiente_forzata

        if lesione_id is None:
            lesione_id = _trova_o_crea_lesione(connessione, paziente_id)
            connessione.execute("UPDATE casi SET lesione_id = ? WHERE id = ?", (lesione_id, caso_id))

        # --- Salvataggio del file e della riga in foto_lesioni: avviene
        # SEMPRE, accettata o no, prima di contattare il modello linguistico. ---
        oggi = date.today().isoformat()
        cartella_progetto = PERCORSO_DATABASE.parent.parent
        cartella_uploads = cartella_progetto / "data" / "uploads"
        cartella_uploads.mkdir(parents=True, exist_ok=True)
        nome_file = f"caso{caso_id}_tentativo{tentativo_numero}.png"
        percorso_file = cartella_uploads / nome_file
        percorso_file.write_bytes(dati_immagine)
        percorso_relativo = str(percorso_file.relative_to(cartella_progetto)).replace("\\", "/")

        if esito_qualita["utilizzabile"]:
            note_qualita = None
        elif qualita_insufficiente_forzata:
            note_qualita = f"Accettata dopo {tentativo_numero} tentativi: qualità insufficiente ({esito_qualita['problema']})."
        else:
            note_qualita = f"Rifiutata: {esito_qualita['problema']}"

        connessione.execute(
            """INSERT INTO foto_lesioni (lesione_id, percorso_file, data_scatto, qualita_ok, note_qualita)
               VALUES (?, ?, ?, ?, ?)""",
            (lesione_id, percorso_relativo, oggi, 1 if accettata else 0, note_qualita),
        )

        if qualita_insufficiente_forzata:
            connessione.execute(
                "UPDATE casi SET stato = 'in_coda_dermatologo', qualita_foto_insufficiente = 1 WHERE id = ?",
                (caso_id,),
            )
        elif esito_qualita["utilizzabile"]:
            riga_stato = connessione.execute("SELECT stato FROM casi WHERE id = ?", (caso_id,)).fetchone()
            if riga_stato[0] == "attesa_foto":
                connessione.execute("UPDATE casi SET stato = 'foto_ricevuta' WHERE id = ?", (caso_id,))

        connessione.commit()
    finally:
        connessione.close()

    # --- Messaggio per il paziente: SOLO qui entra (eventualmente) il modello
    # linguistico, solo per formulare la frase. ---
    if esito_qualita["utilizzabile"]:
        testo_paziente, fonte_testo, modello_usato = _MESSAGGIO_ACCETTATA, "riserva", None
    elif qualita_insufficiente_forzata:
        testo_paziente, fonte_testo, modello_usato = _MESSAGGIO_ACCETTATA_QUALITA_INSUFFICIENTE, "riserva", None
    else:
        testo_paziente, fonte_testo, modello_usato = _genera_messaggio_correzione(esito_qualita["problema"])

    # --- Registro: sempre scritto, ogni tentativo, riuscito o fallito. ---
    input_dati = (
        f"Tentativo {tentativo_numero} — nitidezza {esito_qualita['nitidezza']:.1f}, "
        f"luminosità {esito_qualita['luminosita']:.1f}, "
        f"risoluzione {esito_qualita['larghezza']}x{esito_qualita['altezza']}"
    )
    if esito_qualita["utilizzabile"]:
        decisione = "Foto accettata"
    elif qualita_insufficiente_forzata:
        decisione = f"Foto accettata dopo {tentativo_numero} tentativi: qualità insufficiente, inviata al dermatologo"
    else:
        decisione = f"Foto rifiutata (tentativo {tentativo_numero}/{TENTATIVI_MASSIMI}, problema: {esito_qualita['problema']})"

    motivo = f"Valori misurati — nitidezza: {esito_qualita['nitidezza']:.1f}, luminosità: {esito_qualita['luminosita']:.1f}, risoluzione: {esito_qualita['larghezza']}x{esito_qualita['altezza']}."
    if fonte_testo == "modello":
        motivo += f" [Messaggio per il paziente generato dal modello {modello_usato}.]"
    elif not esito_qualita["utilizzabile"]:
        motivo += " [Messaggio per il paziente generato con contenuto di riserva: modello linguistico non disponibile.]"

    registra_azione(
        agente=NOME_AGENTE,
        input_dati=input_dati,
        decisione=decisione,
        motivo=motivo,
        caso_id=caso_id,
    )

    return {
        "caso_id": caso_id,
        "tentativo_numero": tentativo_numero,
        "tentativi_massimi": TENTATIVI_MASSIMI,
        "accettata": accettata,
        "qualita_insufficiente_forzata": qualita_insufficiente_forzata,
        "problema": esito_qualita["problema"],
        "nitidezza": esito_qualita["nitidezza"],
        "luminosita": esito_qualita["luminosita"],
        "larghezza": esito_qualita["larghezza"],
        "altezza": esito_qualita["altezza"],
        "testo_paziente": testo_paziente,
        "fonte_testo": fonte_testo,
        "modello_usato": modello_usato,
    }
