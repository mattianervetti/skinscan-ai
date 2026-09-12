"""
Dati fissi dei 4 pazienti demo (Marta, Luca, Paolo, Giulia) e generazione delle
immagini sintetiche delle lesioni. Tenuto separato da nucleo/database.py, che
resta generico e non conosce il contenuto specifico della demo.
"""

import math
import random
import sqlite3
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

_CARTELLA_PROGETTO = Path(__file__).resolve().parent.parent
CARTELLA_IMMAGINI_DEMO = _CARTELLA_PROGETTO / "data" / "demo" / "immagini"

_DATA_CREAZIONE = "2026-09-01"
_DATA_COMPILAZIONE_QUESTIONARIO = "2026-09-01"

# Dati anagrafici e questionario dei 4 pazienti demo, coerenti con il livello di
# rischio che dovranno produrre quando l'agente ACCOGLIENZA (Fase 2) li elaborerà.
_PAZIENTI_DEMO = [
    {
        "nome": "Marta",
        "eta": 34,
        "fototipo": 2,
        "categoria_nei": ">50",
        "familiarita_melanoma": 1,
        "melanoma_pregresso": 0,
        "immunosoppressione": 0,
        "neo_cambiato": 1,
    },
    {
        "nome": "Luca",
        "eta": 41,
        "fototipo": 4,
        "categoria_nei": "<20",
        "familiarita_melanoma": 0,
        "melanoma_pregresso": 0,
        "immunosoppressione": 0,
        "neo_cambiato": 0,
    },
    {
        "nome": "Paolo",
        "eta": 58,
        "fototipo": 2,
        "categoria_nei": "20-50",
        "familiarita_melanoma": 1,
        "melanoma_pregresso": 0,
        "immunosoppressione": 0,
        "neo_cambiato": 0,
    },
    {
        "nome": "Giulia",
        "eta": 29,
        "fototipo": 3,
        "categoria_nei": "20-50",
        "familiarita_melanoma": 0,
        "melanoma_pregresso": 0,
        "immunosoppressione": 0,
        "neo_cambiato": 1,
    },
]


def _disegna_lesione_sintetica(percorso_file: Path, seed: int, raggio_base: int) -> None:
    """Genera un'immagine chiaramente artificiale (non una foto clinica reale):
    una forma scura irregolare su sfondo chiaro color pelle, che simula un neo.
    Lo stesso seed produce sempre la stessa forma "di base" (utile per rappresentare
    la stessa lesione fotografata in momenti diversi)."""
    generatore = random.Random(seed)
    dimensione = 300
    immagine = Image.new("RGB", (dimensione, dimensione), color=(235, 200, 175))
    disegno = ImageDraw.Draw(immagine)

    centro_x, centro_y = dimensione // 2, dimensione // 2
    numero_punti = 14
    punti = []
    for indice in range(numero_punti):
        angolo = (2 * math.pi * indice) / numero_punti
        raggio = raggio_base + generatore.randint(-12, 12)
        x = centro_x + raggio * math.cos(angolo)
        y = centro_y + raggio * math.sin(angolo)
        punti.append((x, y))

    colore_lesione = (60, 40, 30)
    disegno.polygon(punti, fill=colore_lesione)

    percorso_file.parent.mkdir(parents=True, exist_ok=True)
    immagine.save(percorso_file)


def _crea_versione_sfocata(percorso_originale: Path, percorso_sfocato: Path) -> None:
    """Crea una copia sfocata di un'immagine esistente, per dimostrare il rifiuto
    di una foto di scarsa qualità da parte dell'agente GUIDA ALLA FOTO."""
    with Image.open(percorso_originale) as immagine:
        immagine_sfocata = immagine.filter(ImageFilter.GaussianBlur(radius=8))
        immagine_sfocata.save(percorso_sfocato)


def _crea_versione_scura(percorso_originale: Path, percorso_scura: Path, fattore: float = 0.10) -> None:
    """Crea una copia sottoesposta (troppo scura) di un'immagine esistente, per
    testare il rifiuto per luminosità insufficiente."""
    with Image.open(percorso_originale) as immagine:
        immagine_scura = ImageEnhance.Brightness(immagine).enhance(fattore)
        immagine_scura.save(percorso_scura)


def _crea_versione_chiara(percorso_originale: Path, percorso_chiara: Path, fattore: float = 2.6) -> None:
    """Crea una copia sovraesposta (troppo chiara) di un'immagine esistente, per
    testare il rifiuto per eccesso di luminosità."""
    with Image.open(percorso_originale) as immagine:
        immagine_chiara = ImageEnhance.Brightness(immagine).enhance(fattore)
        immagine_chiara.save(percorso_chiara)


def _crea_versione_a_bassa_risoluzione(percorso_originale: Path, percorso_bassa: Path, lato: int = 80) -> None:
    """Crea una copia a risoluzione ridotta di un'immagine esistente, per testare
    il rifiuto per immagine troppo piccola."""
    with Image.open(percorso_originale) as immagine:
        immagine_piccola = immagine.resize((lato, lato))
        immagine_piccola.save(percorso_bassa)


def genera_immagini_demo() -> dict[str, Path]:
    """Genera (se non esistono già su disco) le immagini sintetiche della demo
    e restituisce un dizionario {nome_logico: percorso}."""
    percorsi = {
        "marta_precedente": CARTELLA_IMMAGINI_DEMO / "marta_2026-03-10_precedente.png",
        "marta_nitida": CARTELLA_IMMAGINI_DEMO / "marta_2026-09-01_nitida.png",
        "marta_sfocata": CARTELLA_IMMAGINI_DEMO / "marta_2026-09-01_sfocata.png",
        "giulia_nitida": CARTELLA_IMMAGINI_DEMO / "giulia_2026-09-01_nitida.png",
        "paolo_nitida": CARTELLA_IMMAGINI_DEMO / "paolo_2026-09-01_nitida.png",
        # Varianti aggiuntive derivate da marta_nitida, per verificare (e coprire
        # con test) tutti e 4 i percorsi di rifiuto dell'agente GUIDA ALLA FOTO,
        # non solo la sfocatura.
        "marta_troppo_scura": CARTELLA_IMMAGINI_DEMO / "marta_2026-09-01_troppo_scura.png",
        "marta_troppo_chiara": CARTELLA_IMMAGINI_DEMO / "marta_2026-09-01_troppo_chiara.png",
        "marta_risoluzione_bassa": CARTELLA_IMMAGINI_DEMO / "marta_2026-09-01_risoluzione_bassa.png",
    }

    # Marta: stesso seed nella foto precedente e in quella attuale, ma raggio maggiore
    # nella foto attuale, per rappresentare visivamente un neo che è cresciuto/cambiato.
    if not percorsi["marta_precedente"].exists():
        _disegna_lesione_sintetica(percorsi["marta_precedente"], seed=1, raggio_base=28)
    if not percorsi["marta_nitida"].exists():
        _disegna_lesione_sintetica(percorsi["marta_nitida"], seed=1, raggio_base=42)
    if not percorsi["marta_sfocata"].exists():
        _crea_versione_sfocata(percorsi["marta_nitida"], percorsi["marta_sfocata"])

    if not percorsi["giulia_nitida"].exists():
        _disegna_lesione_sintetica(percorsi["giulia_nitida"], seed=2, raggio_base=35)

    if not percorsi["paolo_nitida"].exists():
        _disegna_lesione_sintetica(percorsi["paolo_nitida"], seed=3, raggio_base=38)

    if not percorsi["marta_troppo_scura"].exists():
        _crea_versione_scura(percorsi["marta_nitida"], percorsi["marta_troppo_scura"])
    if not percorsi["marta_troppo_chiara"].exists():
        _crea_versione_chiara(percorsi["marta_nitida"], percorsi["marta_troppo_chiara"])
    if not percorsi["marta_risoluzione_bassa"].exists():
        _crea_versione_a_bassa_risoluzione(percorsi["marta_nitida"], percorsi["marta_risoluzione_bassa"])

    return percorsi


def _crea_lesione(connessione: sqlite3.Connection, paziente_id: int, etichetta: str) -> int:
    cursore = connessione.execute(
        "INSERT INTO lesioni (paziente_id, etichetta, data_creazione) VALUES (?, ?, ?)",
        (paziente_id, etichetta, _DATA_CREAZIONE),
    )
    return cursore.lastrowid


def _crea_foto(
    connessione: sqlite3.Connection,
    lesione_id: int,
    percorso_file: Path,
    data_scatto: str,
    qualita_ok: int,
    note_qualita: str | None = None,
) -> int:
    # Percorso salvato relativo alla cartella del progetto, con separatori "/":
    # così il database resta portabile tra Windows e Linux.
    percorso_relativo = percorso_file.relative_to(_CARTELLA_PROGETTO)
    cursore = connessione.execute(
        """INSERT INTO foto_lesioni (lesione_id, percorso_file, data_scatto, qualita_ok, note_qualita)
           VALUES (?, ?, ?, ?, ?)""",
        (lesione_id, str(percorso_relativo).replace("\\", "/"), data_scatto, qualita_ok, note_qualita),
    )
    return cursore.lastrowid


def popola_dati_demo(connessione: sqlite3.Connection) -> None:
    """Inserisce i 4 pazienti demo con i loro questionari, le lesioni monitorate
    e le foto associate. Genera anche le immagini sintetiche se non esistono già."""
    percorsi_immagini = genera_immagini_demo()

    id_pazienti = {}
    for dati_paziente in _PAZIENTI_DEMO:
        cursore = connessione.execute(
            "INSERT INTO pazienti (nome, eta, fototipo, data_creazione) VALUES (?, ?, ?, ?)",
            (dati_paziente["nome"], dati_paziente["eta"], dati_paziente["fototipo"], _DATA_CREAZIONE),
        )
        id_paziente = cursore.lastrowid
        id_pazienti[dati_paziente["nome"]] = id_paziente

        connessione.execute(
            """INSERT INTO questionari
               (paziente_id, data_compilazione, fototipo, categoria_nei,
                familiarita_melanoma, melanoma_pregresso, immunosoppressione, neo_cambiato)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id_paziente,
                _DATA_COMPILAZIONE_QUESTIONARIO,
                dati_paziente["fototipo"],
                dati_paziente["categoria_nei"],
                dati_paziente["familiarita_melanoma"],
                dati_paziente["melanoma_pregresso"],
                dati_paziente["immunosoppressione"],
                dati_paziente["neo_cambiato"],
            ),
        )

    # Marta: una lesione con 3 foto (una precedente, una sfocata da rifare, una nitida rifatta).
    id_lesione_marta = _crea_lesione(connessione, id_pazienti["Marta"], "Neo braccio destro")
    _crea_foto(connessione, id_lesione_marta, percorsi_immagini["marta_precedente"], "2026-03-10", qualita_ok=1)
    _crea_foto(
        connessione, id_lesione_marta, percorsi_immagini["marta_sfocata"], "2026-09-01",
        qualita_ok=0, note_qualita="Foto sfocata: da rifare",
    )
    _crea_foto(connessione, id_lesione_marta, percorsi_immagini["marta_nitida"], "2026-09-01", qualita_ok=1)

    # Giulia: una lesione con una foto.
    id_lesione_giulia = _crea_lesione(connessione, id_pazienti["Giulia"], "Neo schiena")
    _crea_foto(connessione, id_lesione_giulia, percorsi_immagini["giulia_nitida"], "2026-09-01", qualita_ok=1)

    # Paolo: una lesione con una foto.
    id_lesione_paolo = _crea_lesione(connessione, id_pazienti["Paolo"], "Neo spalla")
    _crea_foto(connessione, id_lesione_paolo, percorsi_immagini["paolo_nitida"], "2026-09-01", qualita_ok=1)

    # Luca: nessuna lesione monitorata, coerente con "nessun sintomo, solo prevenzione".

    connessione.commit()
