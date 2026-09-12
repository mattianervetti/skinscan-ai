"""
Misura della qualità di una foto di una lesione, con OpenCV.

Solo funzioni pure: nessuna dipendenza da Streamlit, dal database o dal modello
linguistico. La qualità è sempre decisa da soglie numeriche esplicite, MAI dal
modello linguistico (vedi CLAUDE.md, principio dell'agente GUIDA ALLA FOTO).

Soglie tarate misurando le immagini demo reali in data/demo/immagini (nitide,
sfocata, troppo scura, troppo chiara, a bassa risoluzione) — non inventate.
Vedi il riepilogo dei valori misurati nel messaggio di approvazione del piano.
"""

import cv2
import numpy as np

# Nitidezza (varianza del Laplaciano): sotto questa soglia la foto è mossa o
# fuori fuoco. Immagini demo nitide: 303-398. Immagine demo sfocata: 0.27.
# Margine enorme in entrambe le direzioni.
SOGLIA_NITIDEZZA_MINIMA = 100.0

# Luminosità media (scala di grigi, 0-255): fuori da questo intervallo la foto
# è troppo scura o troppo chiara per essere valutabile. Immagini demo normali:
# 198-203. Immagine demo troppo scura: 19.96. Immagine demo troppo chiara: 246.56.
SOGLIA_LUMINOSITA_MINIMA = 40.0
SOGLIA_LUMINOSITA_MASSIMA = 235.0

# Risoluzione minima (lato più corto, in pixel): sotto questa soglia l'immagine
# è troppo piccola per essere utile. Immagini demo normali: 300x300. Immagine
# demo a bassa risoluzione: 80x80. Le foto reali da smartphone sono molto più
# grandi: questa è solo una soglia minima per scartare upload palesemente troppo piccoli.
SOGLIA_RISOLUZIONE_MINIMA = 200


def misura_nitidezza(immagine_grigia: np.ndarray) -> float:
    """Varianza del Laplaciano: più è bassa, più l'immagine è mossa/sfocata."""
    return float(cv2.Laplacian(immagine_grigia, cv2.CV_64F).var())


def misura_luminosita(immagine_grigia: np.ndarray) -> float:
    """Luminosità media dell'immagine (0=nero, 255=bianco)."""
    return float(immagine_grigia.mean())


def misura_risoluzione(immagine_grigia: np.ndarray) -> tuple[int, int]:
    """Restituisce (larghezza, altezza) in pixel."""
    altezza, larghezza = immagine_grigia.shape[:2]
    return larghezza, altezza


def valuta_qualita(dati_immagine: bytes) -> dict:
    """Valuta la qualità di una foto a partire dai suoi byte (funziona sia per
    file letti da disco sia per upload/scatti di Streamlit, che forniscono
    entrambi byte).

    Restituisce un dizionario:
        utilizzabile: bool — se la foto supera tutte le soglie
        nitidezza, luminosita: float — valori misurati
        larghezza, altezza: int — dimensioni in pixel
        problema: "troppo_scura" | "troppo_chiara" | "mossa" | "risoluzione_bassa" | None

    Se più problemi sono presenti insieme, viene segnalato quello controllato
    per primo. Ordine scelto DI PROPOSITO: luminosità prima di nitidezza, perché
    una foto molto sottoesposta risulta anche "mossa" per il Laplaciano (il
    contrasto dei bordi crolla insieme alla luce) — controllare prima la
    luminosità evita di etichettare erroneamente come "mossa" una foto che in
    realtà è solo troppo scura.
    """
    array_byte = np.frombuffer(dati_immagine, dtype=np.uint8)
    immagine = cv2.imdecode(array_byte, cv2.IMREAD_COLOR)
    if immagine is None:
        raise ValueError("Impossibile leggere l'immagine: formato non riconosciuto o file corrotto.")

    immagine_grigia = cv2.cvtColor(immagine, cv2.COLOR_BGR2GRAY)

    nitidezza = misura_nitidezza(immagine_grigia)
    luminosita = misura_luminosita(immagine_grigia)
    larghezza, altezza = misura_risoluzione(immagine_grigia)

    problema = None
    if luminosita < SOGLIA_LUMINOSITA_MINIMA:
        problema = "troppo_scura"
    elif luminosita > SOGLIA_LUMINOSITA_MASSIMA:
        problema = "troppo_chiara"
    elif nitidezza < SOGLIA_NITIDEZZA_MINIMA:
        problema = "mossa"
    elif min(larghezza, altezza) < SOGLIA_RISOLUZIONE_MINIMA:
        problema = "risoluzione_bassa"

    return {
        "utilizzabile": problema is None,
        "nitidezza": nitidezza,
        "luminosita": luminosita,
        "larghezza": larghezza,
        "altezza": altezza,
        "problema": problema,
    }
