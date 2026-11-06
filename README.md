# fanano-meteo

Widget Android (KWGT) di sola lettura sulla situazione meteo-idrologica di Fanano (MO):
pioggia osservata, pioggia prevista, livelli dei torrenti Leo e Panaro, stato di allerta della zona E1.

> Lavori in corso: per ora il repository contiene solo la configurazione delle stazioni e la
> diagnostica di raggiungibilità degli endpoint Arpae (`python -m fanano.probe`, workflow `probe`).

## Fonte dei dati

Dati Arpae in tempo reale, non validati.
Fonte: [Allerta Meteo Emilia-Romagna](https://allertameteo.regione.emilia-romagna.it/)
(Arpae Emilia-Romagna - Servizio Idro-Meteo-Clima e Agenzia per la sicurezza territoriale e la protezione civile),
licenza [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Uso personale, non commerciale.
