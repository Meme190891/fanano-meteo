# Taratura della stima "Leo previsto"

Dati scaricati da Arpae Dext3r (https://simc.arpae.it/dext3r/), licenza CC BY-NC-SA 4.0:
livello idrometrico di Fanano (5503, ogni 15') e pioggia cumulata su 30' di Lago Pratignano e Lago Scaffaiolo,
per i due anni nov 2024 - nov 2025 e nov 2025 - nov 2026.

Per rifare la taratura sui due anni (unendo prima i file dei due anni per ogni stazione):

```bash
python calibrazione/taratura_due_anni.py LIVELLO.csv PRATIGNANO.csv SCAFFAIOLO.csv
```

Lo script stampa i coefficienti (salita del Leo per mm di pioggia), la verifica incrociata tra i due anni
(tara su un anno, prova sull'altro), il comportamento sulle piene maggiori e la costante di esaurimento.
I valori scelti sono in `config.yaml`, sezione `previsione_leo`. `taratura.py` e `confronto_pluviometri.py`
sono le analisi del primo anno.

Quando arrivano nuovi dati (per esempio un altro anno), aggiungere i CSV qui e rilanciare lo script:
più piene grandi ci sono nei dati, più la stima vicino alle soglie diventa affidabile.
