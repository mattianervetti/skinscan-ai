"""
Verifica di connessione REALE a Gemini: l'UNICA chiamata vera al modello
linguistico in tutta la cartella test/, isolata apposta in questo file
separato (non si chiama test_*.py: pytest e la suite automatica non lo
trovano e non lo eseguono mai insieme agli altri — vedi CLAUDE.md, sezione 11).

Consuma UNA richiesta di quota sul primo modello disponibile della catena
(CATENA_MODELLI in nucleo/modello_linguistico.py). Da lanciare a mano solo
quando serve verificare davvero la connessione e la chiave API, non a ogni
esecuzione della suite.

Comando per lanciarlo:
    .\\.venv\\Scripts\\python.exe .\\test\\verifica_connessione_gemini.py

Se nel file .env è impostato DISATTIVA_MODELLO=true, questo script fallisce
con un errore chiaro: disattivalo temporaneamente nel .env per usare questo
script, poi riattivalo per tornare a sviluppare senza consumare quota.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.modello_linguistico import CATENA_MODELLI, chiedi_al_modello

if __name__ == "__main__":
    print(f"Catena di modelli configurata: {CATENA_MODELLI}")
    print("Eseguo UNA chiamata reale di prova...")

    risposta, nome_modello = chiedi_al_modello(
        "Rispondi con una sola frase breve in italiano per confermare che la connessione funziona."
    )

    print(f"Modello che ha risposto: {nome_modello}")
    print("Risposta:", risposta)
    assert len(risposta.strip()) > 0

    print("\nCONNESSIONE VERIFICATA")
