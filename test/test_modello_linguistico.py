"""
Test del modulo nucleo/modello_linguistico.py.

Le funzioni test_* (eseguibili anche con pytest) verificano SOLO il meccanismo
della catena di ripiego e l'interruttore per lo sviluppo, tramite simulazioni:
non consumano quota. La verifica con una chiamata reale a Gemini è isolata nel
blocco __main__, così un normale `pytest` non consuma mai quota per sbaglio.

Non stampa mai la chiave API.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

# Permette di importare "nucleo" anche se il test viene lanciato da un'altra cartella.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import modello_linguistico
from nucleo.modello_linguistico import CATENA_MODELLI, chiedi_al_modello, modello_disattivato


class _RispostaFinta:
    def __init__(self, content: str) -> None:
        self.content = content


def _crea_fabbrica_modelli(comportamento_per_modello: dict[str, object], chiamate: list[str]):
    """Restituisce una funzione da usare come sostituto di ChatGoogleGenerativeAI:
    per ogni nome di modello richiesto, restituisce un oggetto finto il cui
    invoke() si comporta secondo comportamento_per_modello (un'eccezione da
    sollevare, oppure il testo di risposta)."""

    def fabbrica(model, google_api_key):
        chiamate.append(model)
        oggetto_finto = type("ModelloFinto", (), {})()
        comportamento = comportamento_per_modello[model]

        def invoke(messaggi, _comportamento=comportamento):
            if isinstance(_comportamento, Exception):
                raise _comportamento
            return _RispostaFinta(_comportamento)

        oggetto_finto.invoke = invoke
        return oggetto_finto

    return fabbrica


def test_passa_al_modello_successivo_se_il_primo_esaurisce_la_quota():
    chiamate: list[str] = []
    comportamento = {
        CATENA_MODELLI[0]: Exception("429 RESOURCE_EXHAUSTED: quota esaurita"),
        CATENA_MODELLI[1]: "risposta di prova",
    }

    with patch("nucleo.modello_linguistico.ChatGoogleGenerativeAI", side_effect=_crea_fabbrica_modelli(comportamento, chiamate)), \
         patch("nucleo.modello_linguistico._ottieni_chiave_api", return_value="chiave-finta"), \
         patch("nucleo.modello_linguistico.modello_disattivato", return_value=False):
        testo, nome_modello = chiedi_al_modello("domanda di prova")

    assert testo == "risposta di prova"
    assert nome_modello == CATENA_MODELLI[1]
    assert chiamate == [CATENA_MODELLI[0], CATENA_MODELLI[1]]  # ha provato il primo, poi è passato al secondo


def test_errore_non_di_quota_non_fa_ciclare_sugli_altri_modelli():
    chiamate: list[str] = []
    comportamento = {CATENA_MODELLI[0]: Exception("chiave API non valida (PERMISSION_DENIED)")}

    with patch("nucleo.modello_linguistico.ChatGoogleGenerativeAI", side_effect=_crea_fabbrica_modelli(comportamento, chiamate)), \
         patch("nucleo.modello_linguistico._ottieni_chiave_api", return_value="chiave-finta"), \
         patch("nucleo.modello_linguistico.modello_disattivato", return_value=False):
        try:
            chiedi_al_modello("domanda di prova")
            assert False, "doveva sollevare RuntimeError"
        except RuntimeError:
            pass

    assert chiamate == [CATENA_MODELLI[0]]  # un solo tentativo: non ha ciclato sugli altri modelli


def test_tutti_i_modelli_esauriti_solleva_errore_di_quota_tradotto():
    chiamate: list[str] = []
    comportamento = {nome: Exception("429 RESOURCE_EXHAUSTED") for nome in CATENA_MODELLI}

    with patch("nucleo.modello_linguistico.ChatGoogleGenerativeAI", side_effect=_crea_fabbrica_modelli(comportamento, chiamate)), \
         patch("nucleo.modello_linguistico._ottieni_chiave_api", return_value="chiave-finta"), \
         patch("nucleo.modello_linguistico.modello_disattivato", return_value=False):
        try:
            chiedi_al_modello("domanda di prova")
            assert False, "doveva sollevare RuntimeError"
        except RuntimeError as errore:
            assert "quota" in str(errore).lower()

    assert chiamate == CATENA_MODELLI  # ha provato tutti i modelli della catena, in ordine


def test_interruttore_disattiva_il_modello(monkeypatch):
    monkeypatch.setenv("DISATTIVA_MODELLO", "true")
    assert modello_disattivato() is True

    try:
        chiedi_al_modello("domanda di prova")
        assert False, "doveva sollevare RuntimeError perché il modello è disattivato"
    except RuntimeError as errore:
        assert "disattivat" in str(errore).lower()

    monkeypatch.setenv("DISATTIVA_MODELLO", "false")
    assert modello_disattivato() is False


if __name__ == "__main__":
    test_passa_al_modello_successivo_se_il_primo_esaurisce_la_quota()
    print("OK - passaggio al modello successivo in caso di quota esaurita")

    test_errore_non_di_quota_non_fa_ciclare_sugli_altri_modelli()
    print("OK - un errore non di quota non fa ciclare sugli altri modelli")

    test_tutti_i_modelli_esauriti_solleva_errore_di_quota_tradotto()
    print("OK - se tutti i modelli sono esauriti l'errore è tradotto correttamente")

    class _FintoMonkeypatch:
        def setenv(self, chiave, valore):
            os.environ[chiave] = valore

    test_interruttore_disattiva_il_modello(_FintoMonkeypatch())
    print("OK - interruttore DISATTIVA_MODELLO funzionante")

    # Unica chiamata REALE di tutto il file: consuma una richiesta di quota sul
    # primo modello della catena. Non aggiungere altre chiamate reali qui sopra.
    print(f"\nCatena di modelli configurata: {CATENA_MODELLI}")
    print("Eseguo UNA chiamata reale di prova...")
    risposta, nome_modello = chiedi_al_modello(
        "Rispondi con una sola frase breve in italiano per confermare che la connessione funziona."
    )
    print(f"Modello che ha risposto: {nome_modello}")
    print("Risposta:", risposta)
    assert len(risposta.strip()) > 0
    print("\nTEST SUPERATO")
