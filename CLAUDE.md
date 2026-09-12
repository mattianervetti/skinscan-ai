# SkinScan AI — Memoria del progetto

## 1. Come lavorare con me
- L'utente si chiama Mattia, non sa programmare e sta imparando. Spiega sempre in italiano semplice, senza gergo non spiegato.
- Non dare mai per scontato un passaggio: se un comando va lanciato, scrivilo per intero.
- Lavoriamo un passo alla volta. Al termine di ogni compito scrivi un riepilogo breve in italiano: cosa hai fatto, quali file hai creato o modificato, come l'utente può verificare che funzioni.
- Se un approccio fallisce due volte, fermati e proponi l'alternativa più semplice, anche se meno elegante.
- Sistema operativo: Windows. Terminale: PowerShell.

## 2. Cos'è SkinScan AI
Piattaforma di prevenzione dermatologica da casa. Il paziente fa tutto dallo smartphone: questionario, foto dei nei guidate dalla piattaforma, esito, eventuale televisita con il dermatologo. Si sposta fisicamente solo se il dermatologo decide una biopsia, presso un centro convenzionato. Target: persone ad alto rischio o con un neo che cambia.

## 3. Vincoli non negoziabili
- COSTO ZERO: solo strumenti e servizi gratuiti.
- PROTOTIPO DIMOSTRATIVO, NON DISPOSITIVO MEDICO: solo pazienti fittizi e immagini dimostrative, nessun dato reale di persone. Ogni schermata dell'app mostra in modo visibile la scritta "Prototipo dimostrativo – non è un dispositivo medico".
- CLASSIFICATORE SIMULATO: una funzione analizza_lesione() restituisce esiti predefiniti per le immagini demo. Deve avere la stessa interfaccia che avrebbe un servizio certificato di terzi in licenza, così da poter essere sostituita senza modificare il resto del sistema. Non va mai presentata come un'analisi reale.
- NESSUNA DECISIONE CLINICA AGLI AGENTI: diagnosi, biopsia e dimissione le decide sempre il dermatologo.
- CHIAVI API: mai scritte dentro il codice, mai in chat, mai su GitHub. Vanno solo in un file .env locale (o nei secrets di Streamlit Cloud), con .env sempre elencato in .gitignore. Verifica questa regola ogni volta che tocchi configurazione o pubblicazione.

## 4. Stack tecnico
Python (versione: 3.14.7), LangGraph per gli agenti, Streamlit per l'interfaccia (con fotocamera nel browser), SQLite per i dati, OpenCV per la qualità delle foto, Git e GitHub per il codice, Streamlit Community Cloud per la pubblicazione.
Modello linguistico: Google Gemini, tramite langchain-google-genai.
Quota: limite giornaliero PER SINGOLO MODELLO su AI Studio (non complessivo): 500 richieste/giorno su gemini-3.5-flash-lite, 20 richieste/giorno sugli altri tre modelli della catena. nucleo/modello_linguistico.py prova una catena di modelli in ordine (CATENA_MODELLI), passando al successivo SOLO se l'errore è di quota esaurita (mai per errore di rete o di chiave, per non ciclare inutilmente). Catena attuale: 1) gemini-3.5-flash-lite, 2) gemini-3-flash-preview, 3) gemini-3.5-flash, 4) gemini-2.5-flash. Nota: "gemini-2.5-flash-lite" e "gemini-3-flash" (nomi mostrati nel pannello quote di AI Studio) NON sono invocabili tramite l'API con questo account (errore 404): verificare di nuovo prima di reinserirli.
Interruttore sviluppo: DISATTIVA_MODELLO=true nel file .env disattiva le chiamate a Gemini, usando sempre i testi di riserva (per lavorare sull'interfaccia senza consumare quota); se attivo, la barra laterale dell'app lo segnala in modo visibile.
Tracciabilità: il testo comunicato al paziente e il modello che l'ha generato restano salvati nel database (tabella casi: testo_paziente, fonte_testo). Una demo dal vivo su un esito già generato in precedenza non consuma quota (si può rivedere senza rigenerarlo).
Regola SSL/chiave: tutte le chiamate al modello linguistico passano da un unico modulo dedicato. È quel modulo, e solo quello, a occuparsi della configurazione SSL (truststore.inject_into_ssl(), racchiuso in un try/except così che su Linux/Streamlit Cloud un eventuale fallimento non blocchi l'avvio), della lettura della chiave da .env e della lettura di DISATTIVA_MODELLO. Nessun altro file del progetto deve farlo direttamente.

## 5. Gli agenti (LangGraph)
1. ACCOGLIENZA — valuta il questionario (fototipo, numero di nei, familiarità, melanoma pregresso, immunosoppressione, neo che cambia) e assegna priorità alta/media/bassa. Se rischio basso e nessun sintomo: solo consigli di prevenzione e promemoria per l'autoesame, nessun esame. → COMPLETATO.
   Regole di triage (nucleo/regole_sicurezza.py, funzioni pure): punteggio di rischio costituzionale (fototipo, numero nei, familiarità, immunosoppressione, età, melanoma pregresso — quest'ultimo vale 5 punti da solo, perché deve bastare per la priorità alta); soglie 0-1 basso, 2-4 medio, 5+ alto. Il "neo cambiato" NON entra nel punteggio: è un interruttore di sicurezza separato che manda SEMPRE al dermatologo, qualunque sia il punteggio.
   Principio: il modello linguistico non decide mai priorità né percorso (li calcola solo il codice) — formula soltanto la spiegazione per il paziente, dopo che la decisione è già presa e salvata.
   Registro comunicativo dei testi per il paziente: sempre "lei"/impersonale, mai il "tu"; nessuna rassicurazione o allarme sull'esito; nessun accordo di genere riferito al paziente (niente forme con "/"); massimo 5 frasi; struttura fissa (cosa è emerso → cosa succede ora → cosa fare); ricorda sempre che la valutazione finale spetta al dermatologo.
2. GUIDA ALLA FOTO — è l'agente più importante. Guida lo scatto (distanza, luce, inquadratura), misura sfocatura e luminosità con OpenCV, fa ripetere la foto finché non è utilizzabile spiegando cosa correggere. Per le zone non visibili suggerisce di farsi aiutare.
3. ANALISI — chiama analizza_lesione() e confronta con le foto precedenti dello stesso paziente.
4. INSTRADAMENTO — mette il caso nella coda del dermatologo per priorità, prenota la televisita su un'agenda simulata, invia notifiche simulate visibili nell'app, sollecita chi non conferma e scala a un operatore umano dopo 2 solleciti. Se serve biopsia, prenota nel centro convenzionato simulato.
5. FOLLOW-UP — chiede il caricamento dell'esito istologico, sollecita se manca, registra in un registro di audit se l'analisi era corretta, programma i controlli periodici.
SUPERVISORE — coordina gli agenti e decide chi agisce.

## 6. Regole di sicurezza scritte nel codice
Queste regole NON vanno affidate al modello linguistico: vanno implementate come controlli espliciti in Python, verificabili e testabili.
- Se il paziente dichiara che un neo è cambiato, il caso va SEMPRE al dermatologo, anche con analisi rassicurante.
- Se il rischio è alto, anche gli esiti rassicuranti passano al dermatologo.
- Ogni azione degli agenti è registrata in un log leggibile (agente, input, decisione, motivo), visibile in una pagina dedicata dell'app.
- Il dermatologo approva o modifica ogni decisione tramite il meccanismo di intervento umano (human-in-the-loop) di LangGraph.

## 7. Interfacce (Streamlit, più pagine)
- Paziente: iscrizione, questionario, scatto guidato, esiti, notifiche, prossimi controlli.
- Dermatologo: coda per priorità, scheda caso (questionario, foto, analisi, storico), decisione.
- Log agenti: sequenza delle azioni, usata durante la presentazione.

## 8. Casi demo (dati fittizi)
- Marta: rischio alto, neo cambiato, prima foto sfocata e rifatta, lesione sospetta, televisita, biopsia, esito caricato.
- Luca: rischio basso, nessun sintomo, riceve solo prevenzione.
- Paolo: non conferma la televisita, 2 solleciti, poi scalato all'operatore umano.
- Giulia: analisi rassicurante ma neo dichiarato cambiato, va comunque al dermatologo.

## 9. Fasi del progetto e stato
0. Preparazione — ambiente, cartella, CLAUDE.md, scelta del modello gratuito. → COMPLETATA
   Decisioni prese: Python 3.14.7 con ambiente virtuale .venv; modello linguistico gemini-2.5-flash (Google Gemini, gratuito); librerie verificate e installate (streamlit, langgraph, langchain-google-genai, python-dotenv, pillow, opencv-python-headless, truststore); connessione a Gemini testata con successo; chiave API gestita solo via .env, mai versionata; repository Git inizializzato in locale.
1. Scheletro — struttura del progetto, database, app Streamlit vuota funzionante. → COMPLETATA
   Costruito: struttura cartelle (pages/, agenti/, nucleo/, data/, test/); nucleo/modello_linguistico.py (unico punto di contatto con Gemini); database SQLite con 12 tabelle, popolato con i 4 pazienti demo (Marta, Luca, Paolo, Giulia) coerenti coi questionari e le lesioni/foto attese; 5 immagini sintetiche generate via codice; resetta_database() per ripristinare la demo; app Streamlit a 4 pagine (Home, Paziente, Dermatologo, Log agenti) con disclaimer obbligatorio e barra laterale (pulsante "Reimposta demo") centralizzati in interfaccia.py e richiamati da un unico punto di ingresso (app.py), così nessuna pagina futura può dimenticarli; README.md creato per chi arriva al repository senza contesto.
2. Agenti uno alla volta (1→5), ciascuno testato su un caso demo prima del successivo. → IN CORSO (1/5)
   Agente 1 (ACCOGLIENZA) completato — vedi dettagli in sezione 5. Costruiti anche: nucleo/registro_azioni.py (log leggibile delle azioni, tabella log_agenti); catena di modelli con ripiego automatico su errore di quota (sezione 4); interruttore DISATTIVA_MODELLO per lo sviluppo; funzione rigenera_testo_paziente() per rigenerare un esito senza aprire un nuovo caso. Pagine Paziente e Log Agenti collegate a dati reali (non più segnaposto).
3. Supervisore e flusso completo con intervento del dermatologo. → da fare
4. Interfacce rifinite e 4 casi demo completi. → da fare
5. Pubblicazione online e checklist per la demo dal vivo (incluso video di riserva registrato). → da fare

App online (Streamlit Community Cloud): https://skinscan-ai-2ehqokwuaoreezapnmoicw.streamlit.app/
Repository GitHub: https://github.com/mattianervetti/skinscan-ai
Nota: Streamlit Community Cloud esegue Python 3.14.7, la stessa versione usata in locale.
ATTENZIONE: la chiave API di Gemini NON è ancora configurata nei secrets dell'app online. Va aggiunta prima della Fase 2, quando gli agenti inizieranno a usare il modello linguistico.
Procedura di pubblicazione aggiornamenti: commit e push sul ramo main su GitHub — Streamlit Community Cloud rileva il push e si aggiorna da solo, senza bisogno di altre azioni.

## 10. Regole operative
- Ogni cosa che costruisci va testata prima di dichiararla finita: scrivi ed esegui un test o uno script di verifica e mostrami il risultato.
- Al termine di ogni fase aggiorna questo CLAUDE.md con lo stato raggiunto e le decisioni prese, poi fai un commit Git con un messaggio chiaro in italiano.
- Non installare pacchetti non necessari. Tieni sempre aggiornato requirements.txt.
- Non creare file fuori dalla cartella del progetto.

## 11. Comandi utili (PowerShell, dalla cartella del progetto)
- Avviare l'app: `.\.venv\Scripts\python.exe -m streamlit run app.py` (si ferma con Ctrl+C)
- Test modulo Gemini: `.\.venv\Scripts\python.exe .\test\test_modello_linguistico.py`
- Test database: `.\.venv\Scripts\python.exe .\test\test_database.py`
- Test app: `.\.venv\Scripts\python.exe .\test\test_app.py`
