# fanano-meteo

Widget Android (KWGT) di sola lettura sulla situazione meteo-idrologica di **Fanano (MO)**: quanto ha
piovuto, quanto pioverà e come stanno rispondendo i torrenti. Tutti i dati vengono da Arpae, tramite il
portale [Allerta Meteo Emilia-Romagna](https://allertameteo.regione.emilia-romagna.it/).

> **Dati Arpae in tempo reale, non validati.** Elaborazione non ufficiale per uso personale: per decisioni
> di sicurezza fare riferimento ai canali ufficiali (Allerta Meteo Emilia-Romagna, Protezione Civile, Comune).

Per aggiungere il widget al telefono apri **https://meme190891.github.io/fanano-meteo/kwgt.html** dal telefono.

![Widget](https://meme190891.github.io/fanano-meteo/widget43.png)

## Indirizzi pubblici

| Cosa | URL |
|---|---|
| **Istruzioni per aggiungere il widget (da aprire sul telefono)** | https://meme190891.github.io/fanano-meteo/kwgt.html |
| Widget pronto per KWGT | https://meme190891.github.io/fanano-meteo/Fanano_meteo.kwgt |
| Immagine del widget 4×3 (tema chiaro / scuro), quella in uso | `.../widget43.png` · `.../widget43_dark.png` |
| Immagine del widget 4×2 (versione precedente, ancora aggiornata) | `.../widget.png` · `.../widget_dark.png` |
| Dati per il widget | https://meme190891.github.io/fanano-meteo/widget.json |
| Pagina con grafici e tabelle (da aprire toccando il widget) | https://meme190891.github.io/fanano-meteo/index.html |
| Grafico Leo (tema chiaro / scuro) | `.../leo.png` · `.../leo_dark.png` |
| Grafico Panaro (tema chiaro / scuro) | `.../panaro.png` · `.../panaro_dark.png` |
| Storico usato dal sistema | `.../state.json` |

I file si aggiornano da soli ogni 30 minuti.

## Come funziona

```
GitHub Actions (ogni 30', minuti 8 e 38)
  ├─ legge state.json dall'ultima pubblicazione (storico, ultimi dati validi)
  ├─ 8 richieste ad allertameteo.regione.emilia-romagna.it (una per endpoint)
  ├─ python -m fanano.main: storico, cumulate, tendenze, soglie, stato, grafici
  └─ pubblica sul branch gh-pages (un solo commit sovrascritto) ──► GitHub Pages ──► KWGT
```

Nessun server sempre acceso, nessun database: lo stato è il file `state.json` pubblicato insieme al resto.

## Fonti dei dati

Tutto dal portale Allerta Meteo Emilia-Romagna (Arpae e Agenzia regionale di protezione civile).

| Dato | Endpoint (`https://allertameteo.regione.emilia-romagna.it` + …) | Documentato? |
|---|---|---|
| Livelli attuali e soglie 1/2/3 di tutti gli idrometri | `/o/api/allerta/get-sensor-values?variabile=254,0,0/1,-,-,-/B13215&time=<ms>` | no (usato dalla mappa del portale) |
| Serie livello (15', ~48–72 h) | `/o/api/allerta/get-time-series/?stazione=<id>&variabile=254,0,0/1,-,-,-/B13215` | no |
| Serie pioggia oraria (~48–72 h) | `/o/api/allerta/get-time-series/?stazione=<id>&variabile=1,0,3600/1,-,-,-/B13011` | no |
| Stato di allerta (oggi; domani con `?data=AAAA-MM-GG%2012:00`) | `/o/get-stato-allerta` | **sì**, [guida sviluppatori](https://allertameteo.regione.emilia-romagna.it/sviluppatori) |
| Previsione ufficiale per provincia (testo + mm per giorno) | `/previsioni-regionali?p_p_id=AllertaPrevisioniTerritorioPortlet&…&_AllertaPrevisioniTerritorioPortlet_prov=MO` | no (pagina HTML) |

- **robots.txt** del portale: `User-Agent: * / Disallow:`, cioè tutto consentito.
- **Licenza**: contenuti e servizi web del portale sono [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
  ([note legali](https://allertameteo.regione.emilia-romagna.it/note-legali)). Va citata la fonte
  "Allerta Meteo Emilia-Romagna" con l'URL, non sono ammessi usi commerciali e i dati rielaborati vanno
  ridistribuiti con la stessa licenza. I file pubblicati riportano l'attribuzione e `LICENZA-DATI.txt`
  (vedi `DATA-LICENSE`).
- Richieste: User-Agent identificativo, timeout 20 s, un solo nuovo tentativo per errori di rete o 5xx, ogni
  URL al massimo una volta per esecuzione (ogni 30 minuti).
- Fonti valutate e scartate:
  - open data `dati-simc.arpae.it/.../realtime.jsonl`: solo ~6 ore, e dai runner GitHub risponde 403;
  - `dati.arpae.it`: irraggiungibile dall'ambiente di sviluppo;
  - modello COSMO (GRIB): troppo pesante per questo sistema.

## Stazioni

| Ruolo | Nome Arpae | ID | Tipo | Corso d'acqua | Comune | Lat / Lon | Quota | Soglie 1/2/3 |
|---|---|---|---|---|---|---|---|---|
| Torrente 1 | Fanano | 5503 | idrometro | T. Leo | Fanano | 44.20386 / 10.79909 | 512 m | 1.0 / 1.3 / 2.0 m |
| Torrente 2 | Ponte Val di Sasso | 5434 | idrometro | F. Panaro (a valle della confluenza Leo–Scoltenna) | Sestola | 44.27258 / 10.81881 | 367 m | 2.0 / 2.8 / 4.0 m |
| Pioggia 1 | Lago Pratignano | 5501 | pluviometro | bacino Panaro | Fanano | 44.17740 / 10.81780 | 1319 m | — |
| Pioggia 2 | Lago Scaffaiolo | 12461 | pluviometro | bacino Panaro (crinale) | Fanano | 44.11918 / 10.80903 | 1794 m | — |

- **Ospitale e Fellicarolo non hanno idrometri Arpae.** I due torrenti confluiscono a formare il Leo, quindi
  la stazione più vicina e significativa per entrambi è "Fanano" sul Leo.
- **Non verificato:** se l'idrometro 5503 è a valle della confluenza (e quindi misura entrambi) o appena a monte.
- Corso d'acqua, comune e bacino sono ricavati dai layer cartografici del portale. Le soglie vengono rilette
  da Arpae a ogni esecuzione.

## Modificare stazioni e regole

Tutta la configurazione è in [`config.yaml`](config.yaml), senza toccare il codice.

- **Torrenti** (`torrenti:`): ogni voce ha `chiave` (prefisso delle chiavi in `widget.json` e nome del PNG),
  `nome`, `nome_breve`, `id` Arpae e i `pluviometri` da mostrare nel grafico.
- **Pluviometri** (`pluviometri:`): `chiave`, `nome`, `nome_breve`, `sigla` (usata nelle righe compatte) e `id`.
- **Previsione**: `provincia` (sigla) e `zona` (`rilievi` o `pianura`). **Allerta**: `zona_allerta`.
- **Regole** (`regole:`): soglie di tendenza, dato vecchio, pioggia abbondante, ora di cambio della previsione…
- **Colori** (`colori:`): verde / giallo / arancio / rosso / grigio, usati da widget e grafici.

Per trovare l'ID di una stazione (elenco ordinato per distanza da Fanano):

```bash
python -m fanano.arpae --elenca idrometri
```

```bash
python -m fanano.arpae --elenca pluviometri --cerca sestola
```

Dopo una modifica fai commit e push su `main`. La prossima esecuzione usa la nuova configurazione e il
workflow `tests` controlla che il file sia valido. I test usano una copia congelata
(`tests/config_test.yaml`), quindi non si rompono se cambi le stazioni. Aggiungere un torrente aggiunge
le chiavi `<chiave>_…` in `widget.json` e il grafico `<chiave>.png`; nel widget vanno aggiunte a mano le righe.

## Regole di calcolo

Tutte le soglie numeriche sono in `config.yaml` (sezione `regole`).

- **Cumulate di pioggia** (per pluviometro): somma dei valori orari Arpae nelle ultime 1/6/24/72 ore,
  fino all'ultimo dato disponibile. Arpae fornisce solo 48–72 ore di serie, quindi lo storico viene conservato
  in `state.json` (ultime 96 ore). Se mancano ore il valore ha un asterisco (es. `7.6*`) e
  `<pluviometro>_72h_parziale` è `true`.
- **Tendenza 3h**: livello attuale meno il livello di circa 3 ore prima (campione entro ±20 minuti).
  Una variazione di +0.05 m o più è "su" (↑), di −0.05 m o meno è "giù" (↓), altrimenti "stabile" (→).
- **Stato soglie**: livello ≥ soglia 3 → "soglia 3" rosso; ≥ soglia 2 → arancio; ≥ soglia 1 → giallo;
  sotto → "normale" verde; nessun dato → "n.d." grigio. Una soglia 0 di Arpae vale "non definita".
- **Previsione** (bollettino Arpae per la provincia di Modena, colonna "rilievi", mm min–max per giorno di
  calendario): `prev_24h` = oggi fino alle 14:00, poi domani; `prev_72h` = somma di oggi, domani e dopodomani
  (con asterisco se manca un giorno). I giorni sono abbinati per data, non per posizione nella pagina.
- **Allerta** (zona E1): si usa il documento valido in questo momento; colore = il peggiore tra gli eventi.
- **Dato vecchio**: dato osservato con più di 2 ore; previsione che non contiene oggi o scaricata da più di
  24 ore; nessun documento di allerta valido adesso.
- **Stato complessivo**: vince il livello più alto; a parità di livello vince la regola con il numero più basso.
  Gli altri messaggi finiscono in `stato_dettaglio`.

  | # | Regola | Livello |
  |---|---|---|
  | 1 | un torrente sopra soglia 1 / 2 / 3 | giallo / arancio / rosso |
  | 2 | allerta zona E1 gialla / arancione / rossa per idraulica, idrogeologica o temporali | giallo / arancio / rosso |
  | 3 | un torrente in tendenza "su" | giallo |
  | 4 | pioggia osservata 24h ≥ 30 mm in uno dei pluviometri | giallo |
  | 5 | pioggia prevista (massimo rilievi) oggi o domani ≥ 30 mm | giallo |
  | 6 | nessuna regola attiva e tutti i dati vecchi | grigio, "Dati non aggiornati" |
  | 7 | altrimenti | verde, "Tutto regolare" (con " · alcuni dati vecchi" se qualche fonte è vecchia) |

- **Fallback**: ogni fonte è indipendente. Se non risponde, o risponde con dati inutilizzabili, resta
  l'ultimo dato valido con il suo orario originale, il flag `*_vecchio` scatta dopo 2 ore e l'errore compare
  in `errori`. `widget.json` resta sempre valido e completo. Se la generazione fallisce del tutto, il workflow
  non pubblica e restano online i file precedenti.

## Chiavi di widget.json

Tutti i valori sono già formattati (testo), tranne i flag `true`/`false` e `stato_livello`.

| Chiavi | Esempio | Significato |
|---|---|---|
| `aggiornato`, `aggiornato_iso` | `06/11 12:10` | ora della generazione (ora italiana) |
| `stato`, `stato_colore`, `stato_livello` | `Tutto regolare`, `#0CA30C`, `0` | stato complessivo; livello −1 grigio, 0 verde, 1 giallo, 2 arancio, 3 rosso |
| `stato_dettaglio` | `Leo sopra soglia 1; Leo in crescita` | tutti i messaggi attivi |
| `dato_vecchio`, `errori` | `false`, `""` | almeno una fonte vecchia; fonti non raggiunte in questa esecuzione |
| `leo_livello`, `leo_freccia`, `leo_tendenza`, `leo_delta3h` | `-0.45 m`, `→`, `stabile`, `+0.02 m` | livello e tendenza 3h |
| `leo_soglia`, `leo_colore`, `leo_soglie` | `normale`, `#0CA30C`, `1.0 / 1.3 / 2.0 m` | stato rispetto alle soglie |
| `leo_ora`, `leo_vecchio`, `leo_grafico` | `11:30`, `false`, URL | ora dell'ultimo dato, flag, URL del PNG |
| `panaro_…` | | come `leo_…` |
| `pratignano_1h` … `_72h`, `_72h_parziale` | `0.2`, `3.0`, `3.6`, `7.6*` | cumulate in mm (`*` = storico incompleto) |
| `pratignano_ora`, `pratignano_vecchio` | `11:00`, `false` | ultimo dato orario |
| `scaffaiolo_…` | | come `pratignano_…` |
| `prev_oggi`, `prev_domani`, `prev_dopodomani` | `4-5 mm`, `0 mm` | previsione per giorno (min–max rilievi MO) |
| `prev_24h`, `prev_24h_etichetta`, `prev_72h` | `4-5 mm`, `oggi`, `4-5 mm` | vedi regole |
| `prev_testo`, `prev_aggiornata`, `prev_vecchio` | testo breve, `12:10`, `false` | descrizione del giorno di `prev_24h` |
| `allerta_oggi`, `allerta_oggi_colore`, `allerta_oggi_eventi` | `verde`, `#0CA30C`, `""` | allerta zona E1 (colore peggiore, eventi non verdi) |
| `allerta_domani`, `allerta_domani_colore` | `verde` o `non ancora emessa` | |
| `allerta_titolo`, `allerta_link`, `allerta_emessa`, `allerta_vecchio` | | documento Arpae |
| `riga_leo`, `riga_panaro` | `Leo -0.45 m →` | righe pronte (`!` finale = dato vecchio) |
| `riga_pioggia` | `1h/24h mm: Prat. 0.2/3.6 · Scaff. 0.6/3.6` | |
| `riga_previsione` | `Prev. oggi 4-5 · dom. 0 · 3gg 4-5 mm` | |
| `riga_allerta`, `riga_aggiornamento` | `Allerta E1: oggi verde · domani verde`, `Agg. 12:10 · Arpae, non validati` | |
| `nota_torrenti`, `pagina`, `disclaimer`, `fonte` | | testi fissi e URL della pagina |

## Guida al widget KWGT

**Il modo più semplice:** apri dal telefono **https://meme190891.github.io/fanano-meteo/kwgt.html** e segui i passi.
Il widget è un'unica immagine (`widget.png`, o `widget_dark.png` con il tema scuro) che il server ridisegna ogni
30 minuti, quindi in KWGT non serve comporre testi e formule.

- **Metodo 1, a mano (6 passi, funziona con KWGT gratuito):**
  1. Aggiungi un widget KWGT 4×3 e toccalo.
  2. **+** → **Immagine**.
  3. **Bitmap** → formula → incolla il testo indicato nella pagina.
  4. **Larghezza** → formula → incolla `$mu(min, si(rwidth), si(rheight) * 4 / 3)$`.
  5. Facoltativo: tocco → *Open link* → `index.html`.
  6. Salva.

  La pagina ha i pulsanti "Copia" per ogni testo.
- **Metodo 2, file pronto (richiede KWGT PRO):** scarica `Fanano_meteo.kwgt`, aggiungi un widget KWGT 4×2,
  toccalo → **Load Preset** → icona della cartella → **Import** → scegli il file in Download → salva.
  - Secondo la [documentazione di Kustom](https://docs.kustom.rocks/docs/general_information/cracked_free/),
    creare un widget da zero è sempre gratis, mentre importare un preset fatto da altri richiede la chiave PRO
    (pagamento unico).
  - Il file contiene un solo elemento immagine e il tocco che apre `index.html`. Il formato `.kwgt` non è
    documentato ufficialmente: il file ricalca la struttura di preset reali esportati da KWGT (versione 13), ma
    non è stato provato su un telefono.

L'immagine dice tutto quello che serve: stato complessivo, livelli e tendenze di Leo e Panaro con il colore della
soglia, pioggia 1h/24h, previsione, allerta, ora dell'aggiornamento (in rosso se i dati sono vecchi).

### Avanzato (facoltativo): widget composto da testi

Chi preferisce un widget fatto di testi veri, con dimensioni e colori personalizzabili, può costruirlo leggendo
`widget.json`. Le formule sono verificate sulla [documentazione Kustom](https://docs.kustom.rocks/):
[`wg`](https://docs.kustom.rocks/docs/reference/functions/wg/) (JSON con espressione JSONPath),
[`gv`](https://docs.kustom.rocks/docs/reference/functions/gv/) (variabili globali),
[`si(darkmode)`](https://docs.kustom.rocks/docs/reference/functions/si/),
[`df(S)`](https://docs.kustom.rocks/docs/reference/functions/df/) (secondi Unix) e
[`mu(floor, …)`](https://docs.kustom.rocks/docs/reference/functions/mu/).
I nomi delle voci di menu possono variare leggermente tra versioni e lingue dell'app.

#### 1. Crea il widget

1. Installa **KWGT** dal Play Store.
2. Tieni premuto sulla home → **Widget** → **KWGT** → scegli la misura **4×2** e posizionalo.
3. Tocca il widget vuoto: si apre l'editor di KWGT. Crea un preset vuoto.

#### 2. Variabile globale con l'URL (gestisce anche l'aggiornamento)

KWGT riscarica un contenuto web quando cambia il suo URL: è il metodo indicato dalla
[ricetta ufficiale](https://docs.kustom.rocks/categories/Web-Content/), che aggiunge un parametro
`?refresh=` all'URL. Qui il parametro cambia ogni 30 minuti, alle :15 e alle :45, cioè dopo le pubblicazioni
delle :08 e :38.

Nell'elemento radice → tab **Globals** → **+** → tipo **Text** → nome `url` → valore:

```
https://meme190891.github.io/fanano-meteo/widget.json?t=$mu(floor, (df(S) - 900) / 1800)$
```

Se la tua versione non valuta le formule dentro le globali, usa l'URL completo direttamente in ogni formula, così:
`$wg("https://meme190891.github.io/fanano-meteo/widget.json?t=" + mu(floor, (df(S) - 900) / 1800), json, .stato)$`

#### 3. Struttura

- **Sfondo:** un modulo **Shape** (rettangolo) a tutta dimensione, angoli arrotondati ~20, colore
  semitrasparente, per esempio `#B3141414` (scuro) oppure `#E0FCFCFB` (chiaro); il formato è `#AARRGGBB`.
- **Contenuto:** sopra lo sfondo, un **Stack Group** verticale con 7 righe, come nell'immagine in cima a
  questo file.
- **Righe con pallino colorato** (1, 3, 5, 9): uno Stack Group orizzontale con una Shape (cerchio ~10) e
  uno o più Text.
- **Colori da formula:** nella proprietà del colore tocca l'icona della formula (calcolatrice) e incolla la
  formula `…_colore`.

#### 4. Formule (il numero corrisponde all'immagine)

| # | Elemento | Formula |
|---|---|---|
| 1 | pallino stato (colore) | `$wg(gv(url), json, .stato_colore)$` |
| 1 | testo stato | `$wg(gv(url), json, .stato)$` |
| 2 | ora aggiornamento (a destra) | `$tc(cut, wg(gv(url), json, .aggiornato), -5)$` |
| 3 | Leo: livello e freccia | `$wg(gv(url), json, .riga_leo)$` (oppure `.leo_livello` e `.leo_freccia` separati) |
| 4 | Leo: pallino (colore) | `$wg(gv(url), json, .leo_colore)$` |
| 4 | Leo: stato soglia | `$wg(gv(url), json, .leo_soglia)$` |
| 5 | Panaro: livello e freccia | `$wg(gv(url), json, .riga_panaro)$` |
| 6 | Panaro: pallino / stato | `$wg(gv(url), json, .panaro_colore)$` · `$wg(gv(url), json, .panaro_soglia)$` |
| 7 | pioggia osservata | `$wg(gv(url), json, .riga_pioggia)$` |
| 8 | pioggia prevista | `$wg(gv(url), json, .riga_previsione)$` |
| 9 | allerta: pallino / testo | `$wg(gv(url), json, .allerta_oggi_colore)$` · `$wg(gv(url), json, .riga_allerta)$` |
| 10 | aggiornamento e avviso | `$wg(gv(url), json, .riga_aggiornamento)$` |

Altre formule utili:
- cumulata 72h di Scaffaiolo: `$wg(gv(url), json, .scaffaiolo_72h)$`;
- testo della previsione: `$wg(gv(url), json, .prev_testo)$`;
- testo rosso quando i dati sono vecchi, come formula del colore (`dato_vecchio` arriva come testo
  `true`/`false`): `$if(wg(gv(url), json, .dato_vecchio) = true, #D03B3B, #FFFFFF)$`.

#### 5. Tocco: apri la pagina con i grafici

Sull'elemento radice (o sullo Stack Group) → tab **Touch** → togli l'azione predefinita che apre l'editor →
aggiungi un'azione **Open Link** con URL:

```
https://meme190891.github.io/fanano-meteo/index.html
```

La pagina mostra i grafici nel tema del telefono, le tabelle dei valori e i link ad Arpae.
Su alcuni Xiaomi e OnePlus il tocco funziona solo con Impostazioni di Kustom → **Notification Mode** →
**FORCED** ([documentazione](https://docs.kustom.rocks/docs/common_issues/touch_launch_not_working/)).

#### 6. (Facoltativo) Grafico PNG in un widget

I grafici sono verticali (1080×1330), quindi conviene un secondo widget **4×4** o **4×5**. Aggiungi un
modulo **Image** a tutta larghezza → proprietà **Bitmap** → passa a **formula**:

```
$if(si(darkmode) = 1, "https://meme190891.github.io/fanano-meteo/leo_dark.png", "https://meme190891.github.io/fanano-meteo/leo.png") + "?t=" + mu(floor, (df(S) - 900) / 1800)$
```

Al posto di `leo` puoi mettere `panaro`. `si(darkmode)` vale 1 quando il telefono è in tema scuro.

#### 7. Salva e verifica

Salva con l'icona del dischetto. Se compare testo vuoto o un errore:
- apri https://meme190891.github.io/fanano-meteo/widget.json nel browser per vedere se i dati ci sono;
- controlla di aver scritto `url` uguale in globali e formule;
- escludi KWGT dall'ottimizzazione della batteria, così può aggiornarsi in background.

#### Preset .kwgt

Il preset pronto (`Fanano_meteo.kwgt`, metodo 1) contiene la versione a immagine. Per la versione a testi non
c'è un preset: una volta costruito il widget, conviene esportarlo dal menu dell'editor di KWGT come copia di
sicurezza.

## Limiti

**Dati**
- Dati in tempo reale **non validati**: possono contenere errori o picchi strumentali.
- Livelli, serie e previsione vengono da endpoint e pagine **non documentati**: possono cambiare senza preavviso.
  In quel caso la fonte va in errore, resta l'ultimo dato valido con il flag "vecchio" e il workflow `probe`
  aiuta a capire cosa è cambiato.
- La previsione si ottiene leggendo una pagina HTML: se cambia la struttura, la previsione risulta "n.d." o
  vecchia e l'errore compare in `errori`.
- La previsione è il bollettino per i **rilievi della provincia di Modena** (min–max nell'area, per giorno di
  calendario), non un valore specifico per Fanano né a finestre mobili di 24/72 ore.
- Latenza Arpae di circa 35–45 minuti. Le serie Arpae coprono 48–72 ore: la cumulata 72h è "parziale" nel primo
  giorno di funzionamento o dopo interruzioni lunghe.
- Ospitale e Fellicarolo non sono monitorati. La posizione dell'idrometro 5503 rispetto alla loro confluenza non
  è verificata.
- L'allerta di domani compare dopo l'emissione del bollettino (di solito verso mezzogiorno).

**Hosting (GitHub Actions + Pages)**
- Le esecuzioni pianificate sono *best effort*: ritardi tipici di 5–20 minuti, a volte di più, o esecuzioni
  saltate. Nel widget c'è sempre l'ora dell'ultimo aggiornamento e il flag dei dati vecchi.
- Nei repository pubblici GitHub **disattiva i workflow pianificati dopo 60 giorni senza attività**.
  - Il commit su `gh-pages` di ogni esecuzione e il job `keepalive` del lunedì dovrebbero evitarlo, ma è una
    mitigazione, non una garanzia.
  - Se succede, GitHub manda un'email; si riattiva da Actions → aggiorna → **Enable workflow**.
- GitHub Pages tiene i file in cache 10 minuti. In totale il widget mostra dati vecchi di circa 45–90 minuti.
- Repository e dati sono pubblici, e Pages gratuito lo richiede. Non ci sono segreti né chiavi.
- Se un giorno Arpae bloccasse gli IP di GitHub, il widget continuerebbe a mostrare gli ultimi dati, poi
  passerebbe a grigio con "Dati non aggiornati".
  - Prima verifica: workflow `probe`.
  - Alternative: Cloudflare Workers con cron, oppure una piccola macchina gratuita.

## Manutenzione

- **Esecuzione manuale**: Actions → **aggiorna** → **Run workflow**. L'opzione `simula_arpae_giu` prova il
  fallback con un host inesistente; i dati restano quelli dell'esecuzione precedente.
- **Diagnostica**: Actions → **probe** → **Run workflow**. Mostra una tabella con l'esito di ogni endpoint.
- **In locale** (Python 3.12+):

  ```bash
  pip install -r requirements.txt
  ```

  ```bash
  python -m fanano.main --out out/
  ```

  ```bash
  python -m pytest
  ```

- **Aggiornare le risposte di esempio dei test** (dopo un cambio di formato Arpae): salva le nuove risposte, poi
  aggiorna i valori attesi in `tests/` e `tests/config_test.yaml` se cambi stazioni.

  ```bash
  python -m fanano.arpae --save tests/fixtures
  ```

### Struttura dei file

```
config.yaml                   stazioni, regole, colori, URL di pubblicazione
fanano/arpae.py               URL, download e parsing degli endpoint Arpae (+ --elenca, --save)
fanano/compute.py             storico, cumulate, tendenza, soglie, stato complessivo, fallback
fanano/render.py              grafici PNG, index.html e kwgt.html (istruzioni per il telefono)
fanano/widget_img.py          il widget intero come immagine (widget.png / widget_dark.png)
fanano/kwgt.py                preset KWGT importabile (Fanano_meteo.kwgt)
fanano/main.py                esecuzione completa (online o da cartella di risposte salvate)
fanano/probe.py               diagnostica di raggiungibilità
tests/                        test (parsing, calcoli, fallback, grafici, config) + fixture Arpae reali
.github/workflows/aggiorna.yml  pianificato ogni 30': genera e pubblica su gh-pages; keepalive settimanale
.github/workflows/tests.yml     test a ogni push
.github/workflows/probe.yml     diagnostica manuale
docs/kwgt-layout.png          anteprima del widget composto da testi (sezione avanzata)
DATA-LICENSE                  licenza dei dati pubblicati
```

## Licenza e attribuzione

Dati: © Arpae Emilia-Romagna e Agenzia per la sicurezza territoriale e la protezione civile –
[Allerta Meteo Emilia-Romagna](https://allertameteo.regione.emilia-romagna.it/), licenza
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). I file pubblicati sono una
rielaborazione distribuita con la stessa licenza (vedi [`DATA-LICENSE`](DATA-LICENSE)). Uso personale,
non commerciale.
