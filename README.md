# fanano-meteo

Widget Android (KWGT) di sola lettura sulla situazione meteo-idrologica di Fanano (MO):
pioggia osservata, pioggia prevista, livelli dei torrenti Leo e Panaro, stato di allerta della zona E1.

> Lavori in corso. Per ora il repository contiene:
> - `config.yaml`: stazioni e parametri;
> - `fanano/arpae.py`: download e parsing degli endpoint Arpae (`python -m fanano.arpae` stampa i valori
>   estratti, `--save DIR` salva anche le risposte grezze);
> - `fanano/probe.py`: diagnostica di raggiungibilità (`python -m fanano.probe`, workflow `probe`);
> - `fanano/compute.py` e `fanano/main.py`: storico, cumulate, tendenza, soglie, stato complessivo,
>   fallback; `python -m fanano.main --out out/` genera `out/widget.json` e `out/state.json`;
> - `tests/`: test su risposte Arpae reali salvate in `tests/fixtures` (`python -m pytest`).

## Regole di calcolo

Tutte le soglie numeriche sono in `config.yaml` (sezione `regole`).

- **Cumulate di pioggia** (per pluviometro): somma dei valori orari Arpae nelle ultime 1/6/24/72 ore,
  fino all'ultimo dato disponibile. Arpae fornisce solo 48–72 ore di serie: lo storico viene conservato
  in `state.json` (ultime 96 ore). Se mancano ore il valore ha un asterisco (es. `7.6*`) e
  `<pluviometro>_72h_parziale` è `true`.
- **Tendenza 3h**: livello attuale meno il livello di circa 3 ore prima (campione entro ±20 minuti).
  Una variazione di +0.05 m o più è "su" (↑), di −0.05 m o meno è "giù" (↓), altrimenti "stabile" (→).
- **Stato soglie**: livello ≥ soglia 3 → "soglia 3" rosso; ≥ soglia 2 → arancio; ≥ soglia 1 → giallo;
  sotto → "normale" verde; nessun dato → "n.d." grigio. Soglia 0 di Arpae = non definita.
- **Previsione** (bollettino Arpae provincia di Modena, colonna "rilievi", mm min–max per giorno di calendario):
  `prev_24h` = oggi fino alle 14:00, poi domani; `prev_72h` = somma di oggi, domani e dopodomani
  (asterisco se manca un giorno). I giorni sono abbinati per data, non per posizione nella pagina.
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

- **Fallback**: ogni fonte è indipendente. Se non risponde, o risponde con dati inutilizzabili, si tiene
  l'ultimo dato valido con il suo orario originale, il flag `*_vecchio` scatta dopo 2 ore e l'errore compare
  in `errori`. `widget.json` resta sempre valido e completo.

## Fonte dei dati

Dati Arpae in tempo reale, non validati.
Fonte: [Allerta Meteo Emilia-Romagna](https://allertameteo.regione.emilia-romagna.it/)
(Arpae Emilia-Romagna - Servizio Idro-Meteo-Clima e Agenzia per la sicurezza territoriale e la protezione civile),
licenza [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Uso personale, non commerciale.
