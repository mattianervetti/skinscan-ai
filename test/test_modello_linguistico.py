"""
Test del modulo nucleo/modello_linguistico.py: verifica che una domanda semplice
a Gemini restituisca una risposta non vuota. Non stampa mai la chiave API.
"""

import sys
from pathlib import Path

# Permette di importare "nucleo" anche se il test viene lanciato da un'altra cartella.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.modello_linguistico import chiedi_al_modello, NOME_MODELLO


def test_chiedi_al_modello_restituisce_risposta_non_vuota():
    risposta = chiedi_al_modello(
        "Rispondi con una sola frase breve in italiano per confermare che la connessione funziona."
    )

    assert isinstance(risposta, str)
    assert len(risposta.strip()) > 0


if __name__ == "__main__":
    print(f"Modello usato: {NOME_MODELLO}")
    risposta = chiedi_al_modello(
        "Rispondi con una sola frase breve in italiano per confermare che la connessione funziona."
    )
    print("Risposta:", risposta)
    assert len(risposta.strip()) > 0
    print("TEST SUPERATO")
