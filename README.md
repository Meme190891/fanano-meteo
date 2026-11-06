# fanano-meteo

Widget Android (KWGT) di sola lettura sulla situazione meteo-idrologica di Fanano (MO):
pioggia osservata, pioggia prevista, livelli dei torrenti Leo e Panaro, stato di allerta della zona E1.

> Lavori in corso. Per ora il repository contiene:
> - `config.yaml`: stazioni e parametri;
> - `fanano/arpae.py`: download e parsing degli endpoint Arpae (`python -m fanano.arpae` stampa i valori
>   estratti, `--save DIR` salva anche le risposte grezze);
> - `fanano/probe.py`: diagnostica di raggiungibilità (`python -m fanano.probe`, workflow `probe`);
> - `tests/`: test dei parser sulle risposte Arpae reali salvate in `tests/fixtures` (`python -m pytest`).

## Fonte dei dati

Dati Arpae in tempo reale, non validati.
Fonte: [Allerta Meteo Emilia-Romagna](https://allertameteo.regione.emilia-romagna.it/)
(Arpae Emilia-Romagna - Servizio Idro-Meteo-Clima e Agenzia per la sicurezza territoriale e la protezione civile),
licenza [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Uso personale, non commerciale.
