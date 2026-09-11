# SkinScan AI

Prototipo di piattaforma di prevenzione dermatologica da casa: il paziente compila un questionario, scatta foto guidate dei propri nei e riceve un esito. Se necessario viene messo in contatto con un dermatologo per una televisita, e solo se il dermatologo lo ritiene indispensabile si reca fisicamente in un centro convenzionato per una biopsia.

> ⚠️ **Prototipo dimostrativo a scopo accademico.** Non è un dispositivo medico e non esegue diagnosi. Tutti i pazienti e le immagini presenti sono fittizi. Il classificatore che analizza le lesioni è **simulato**: restituisce esiti predefiniti, non un'analisi clinica reale.

## A cosa serve e come funziona

L'obiettivo è dimostrare come un sistema di agenti automatici possa affiancare (mai sostituire) un dermatologo nella prevenzione del melanoma:

1. Il paziente compila un questionario di valutazione del rischio.
2. Se serve un controllo, l'app lo guida nello scatto di foto utilizzabili (rifiutando quelle sfocate o mal illuminate).
3. Un classificatore simulato analizza la foto e la confronta con quelle precedenti dello stesso paziente.
4. In base a priorità e rischio, il caso viene messo in coda per il dermatologo, che prenota una televisita simulata.
5. Solo il dermatologo, mai il sistema, decide diagnosi, eventuale biopsia e dimissione.
6. Ogni azione compiuta dagli agenti automatici viene registrata in un log leggibile, consultabile nell'app.

## Stack tecnico

- **Python 3.14.7**
- **Streamlit** — interfaccia web (con fotocamera nel browser)
- **LangGraph** — orchestrazione degli agenti
- **Google Gemini** (`gemini-2.5-flash`, tramite `langchain-google-genai`) — modello linguistico
- **SQLite** — dati (pazienti, casi, log, appuntamenti, ecc.)
- **OpenCV / Pillow** — controllo qualità e generazione delle immagini demo
- **Git / GitHub** — versionamento del codice
- **Streamlit Community Cloud** — pubblicazione online (gratuita)

## Eseguire il progetto in locale

Serve Python 3.10 o superiore (il progetto è sviluppato con 3.14.7).

1. **Crea l'ambiente virtuale**, dalla cartella del progetto:
   ```
   python -m venv .venv
   ```
2. **Attivalo** (PowerShell su Windows):
   ```
   .\.venv\Scripts\Activate.ps1
   ```
3. **Installa le librerie**:
   ```
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
4. **Configura la chiave API di Google Gemini.** Il repository include solo `.env.example`, un file di esempio che documenta quali variabili servono, **senza nessuna chiave reale** — la chiave API **non è mai inclusa nel repository**. Per usarla:
   - copia `.env.example` in un nuovo file chiamato `.env` (nella stessa cartella)
   - apri `.env` e sostituisci il segnaposto con una tua chiave Google Gemini reale, ottenuta autonomamente da Google AI Studio:
     ```
     GOOGLE_API_KEY=la_tua_chiave_vera
     ```
   - il file `.env` non va mai condiviso né caricato su GitHub: è già escluso tramite `.gitignore`.
5. **Avvia l'app**:
   ```
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```
   Si apre automaticamente nel browser su `http://localhost:8501`. Per fermarla, premi `Ctrl+C` nel terminale.

### Eseguire i test

```
.\.venv\Scripts\python.exe .\test\test_modello_linguistico.py
.\.venv\Scripts\python.exe .\test\test_database.py
.\.venv\Scripts\python.exe .\test\test_app.py
```

## Stato di avanzamento

| Fase | Contenuto | Stato |
|---|---|---|
| 0 | Preparazione: ambiente, scelta del modello linguistico gratuito | ✅ Completata |
| 1 | Scheletro: struttura del progetto, database, app Streamlit navigabile | ✅ Completata |
| 2 | I 5 agenti, uno alla volta, ciascuno testato su un caso demo | ⬜ Da fare |
| 3 | Supervisore e flusso completo con intervento del dermatologo | ⬜ Da fare |
| 4 | Interfacce rifinite e 4 casi demo completi | ⬜ Da fare |
| 5 | Pubblicazione online e checklist per la demo dal vivo | ⬜ Da fare |
