"""Test di cumulate, tendenza, soglie, formattazione e regole dello stato complessivo."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from fanano import compute
from conftest import NOW

UTC = timezone.utc
T0 = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)


def oraria(valori, inizio=T0):
    return [(inizio + timedelta(hours=i + 1), float(v)) for i, v in enumerate(valori)]


def quarti(valori, fine=T0):
    n = len(valori)
    return [(fine - timedelta(minutes=15 * (n - 1 - i)), float(v)) for i, v in enumerate(valori)]


# ------------------------------------------------------------------ cumulate

def test_cumulata_complete_e_parziali():
    s = oraria([1, 2, 3, 4, 5, 6])
    assert compute.cumulata(s, 1) == (6.0, True)
    assert compute.cumulata(s, 3) == (15.0, True)
    assert compute.cumulata(s, 6) == (21.0, True)
    assert compute.cumulata(s, 24) == (21.0, False)       # storico insufficiente -> parziale


def test_cumulata_con_buco_e_vuota():
    s = oraria([1, 1, 1, 1])
    del s[1]                                              # manca un'ora
    assert compute.cumulata(s, 4) == (3.0, False)
    assert compute.cumulata([], 1) == (None, False)


def test_cumulata_arrotonda():
    assert compute.cumulata(oraria([0.1, 0.2]), 2) == (0.3, True)


# ------------------------------------------------------------------ tendenza

def test_tendenza_su_giu_stabile_ai_bordi():
    base = [-0.50] * 12
    assert compute.tendenza(quarti(base + [-0.45]))[:2] == ("su", "↑")        # +0.05 esatto = su
    assert compute.tendenza(quarti(base + [-0.46]))[:2] == ("stabile", "→")   # +0.04
    assert compute.tendenza(quarti(base + [-0.55]))[:2] == ("giù", "↓")       # -0.05 esatto = giu'
    assert compute.tendenza(quarti(base + [-0.54]))[:2] == ("stabile", "→")
    assert compute.tendenza(quarti(base + [-0.30]))[2] == pytest.approx(0.20)


def test_tendenza_senza_riferimento():
    assert compute.tendenza(quarti([0.1] * 8)) == ("n.d.", "?", None)      # solo 1h45' di storico
    assert compute.tendenza([]) == ("n.d.", "?", None)
    # riferimento a 2h45': entro la tolleranza di 20'
    s = quarti([0.0] * 12)                                # 2h45' di storico
    assert compute.tendenza(s)[0] == "stabile"


# ------------------------------------------------------------------ soglie

@pytest.mark.parametrize("valore, atteso", [
    (-0.45, (0, "normale")), (0.99, (0, "normale")), (1.0, (1, "soglia 1")), (1.29, (1, "soglia 1")),
    (1.3, (2, "soglia 2")), (2.0, (3, "soglia 3")), (5.0, (3, "soglia 3")), (None, (None, "n.d.")),
])
def test_stato_soglie_leo(valore, atteso):
    assert compute.stato_soglie(valore, 1.0, 1.3, 2.0) == atteso


def test_stato_soglie_parziali_o_assenti():
    assert compute.stato_soglie(3.0, None, 2.0, 3.8) == (2, "soglia 2")
    assert compute.stato_soglie(1.0, None, 2.0, 3.8) == (0, "normale")
    assert compute.stato_soglie(1.0, None, None, None) == (None, "senza soglie")


# ------------------------------------------------------------------ storico e formattazione

def test_unisci_serie_nuovo_vince_e_pota():
    vecchia = oraria([1, 1, 1])
    nuova = [(T0 + timedelta(hours=3), 9.0), (T0 + timedelta(hours=4), 2.0)]
    out = compute.unisci_serie(vecchia, nuova, da=T0 + timedelta(hours=2))
    assert out == [(T0 + timedelta(hours=2), 1.0), (T0 + timedelta(hours=3), 9.0), (T0 + timedelta(hours=4), 2.0)]


@pytest.mark.parametrize("pmin, pmax, atteso", [
    (4, 5, "4-5 mm"), (0, 0, "0 mm"), (1.5, 3, "1.5-3 mm"), (10, 15, "10-15 mm"), (None, None, "n.d."), (None, 2, "2 mm"),
])
def test_fmt_range_mm(pmin, pmax, atteso):
    assert compute.fmt_range_mm(pmin, pmax) == atteso


def test_fmt_ora_e_accorcia():
    assert compute.fmt_ora(datetime(2026, 11, 6, 10, 0, tzinfo=UTC), NOW) == "11:00"
    assert compute.fmt_ora(datetime(2026, 11, 5, 22, 0, tzinfo=UTC), NOW) == "05/11 23:00"
    assert compute.fmt_ora(None, NOW) == "n.d."
    assert compute.accorcia("uno due tre quattro", 100) == "uno due tre quattro"
    assert compute.accorcia("uno due, tre quattro", 12) == "uno due…"


# ------------------------------------------------------------------ widget.json dalle risposte reali

CHIAVI_OBBLIGATORIE = {
    "aggiornato", "stato", "stato_colore", "stato_livello", "dato_vecchio", "errori", "disclaimer", "fonte",
    "leo_livello", "leo_tendenza", "leo_freccia", "leo_soglia", "leo_colore", "leo_ora", "leo_vecchio",
    "panaro_livello", "panaro_tendenza", "panaro_soglia", "panaro_colore", "panaro_ora", "panaro_vecchio",
    "pratignano_1h", "pratignano_6h", "pratignano_24h", "pratignano_72h", "pratignano_ora", "pratignano_vecchio",
    "scaffaiolo_1h", "scaffaiolo_6h", "scaffaiolo_24h", "scaffaiolo_72h", "scaffaiolo_ora", "scaffaiolo_vecchio",
    "prev_24h", "prev_72h", "prev_testo", "prev_vecchio", "allerta_oggi", "allerta_oggi_colore", "allerta_vecchio",
}


def widget(st, cfg, now=NOW, errori=None):
    w = compute.costruisci_widget(st, cfg, now, errori)
    json.dumps(w)                          # sempre serializzabile
    return w


def test_widget_da_risposte_reali(stato, cfg):
    w = widget(stato, cfg)
    assert CHIAVI_OBBLIGATORIE <= set(w)
    assert list(w)[:3] == ["aggiornato", "aggiornato_iso", "stato"]
    assert (w["leo_livello"], w["leo_tendenza"], w["leo_delta3h"], w["leo_soglia"]) == ("-0.45 m", "stabile", "+0.02 m", "normale")
    assert (w["leo_colore"], w["leo_ora"], w["leo_vecchio"]) == ("#388E3C", "11:00", False)
    assert (w["panaro_livello"], w["panaro_soglie"]) == ("0.77 m", "2.0 / 2.8 / 4.0 m")
    assert [w[f"pratignano_{h}h"] for h in (1, 6, 24, 72)] == ["0.2", "3.0", "3.6", "7.6*"]
    assert w["pratignano_72h_parziale"] is True
    assert [w[f"scaffaiolo_{h}h"] for h in (1, 6, 24)] == ["0.6", "3.6", "3.6"]
    assert (w["prev_oggi"], w["prev_domani"], w["prev_dopodomani"]) == ("4-5 mm", "0 mm", "0 mm")
    assert (w["prev_24h"], w["prev_24h_etichetta"], w["prev_72h"]) == ("4-5 mm", "oggi", "4-5 mm")
    assert w["prev_testo"].startswith("Al mattino molto nuvoloso") and len(w["prev_testo"]) <= 110
    assert (w["allerta_oggi"], w["allerta_domani"], w["allerta_vecchio"]) == ("verde", "verde", False)
    assert (w["stato"], w["stato_livello"], w["stato_colore"]) == ("Tutto regolare", 0, "#388E3C")
    assert w["disclaimer"] == "Dati Arpae in tempo reale, non validati"
    assert w["leo_grafico"] == "https://meme190891.github.io/fanano-meteo/leo.png"


def test_previsione_24h_passa_a_domani_dopo_le_14(stato, cfg):
    w = widget(stato, cfg, now=datetime(2026, 11, 6, 13, 30, tzinfo=UTC))   # 14:30 ora italiana
    assert (w["prev_24h"], w["prev_24h_etichetta"]) == ("0 mm", "domani")
    assert w["prev_testo"].startswith("Al mattino in pianura")


def test_giorno_dopo_senza_nuovi_dati(stato, cfg):
    w = widget(stato, cfg, now=datetime(2026, 11, 7, 8, 0, tzinfo=UTC))
    assert (w["prev_oggi"], w["prev_domani"], w["prev_dopodomani"]) == ("0 mm", "0 mm", "n.d.")
    assert w["prev_72h"] == "0 mm*"                       # solo 2 giorni disponibili
    assert w["allerta_titolo"].startswith("Bollettino di vigilanza 179/2026")   # il documento di "domani" ora vale oggi
    assert (w["allerta_vecchio"], w["allerta_domani"]) == (False, "non ancora emessa")
    assert w["leo_vecchio"] and w["dato_vecchio"]
    assert w["stato"] == "Tutto regolare · alcuni dati vecchi"


# ------------------------------------------------------------------ regole dello stato complessivo

def imposta_livello(st, chiave, valore, delta_3h=None):
    serie = st["serie"][f"livello_{chiave}"]
    serie[-1][1] = valore
    if delta_3h is not None:
        for p in serie[-13:-1]:                           # ultime 3h prima dell'ultimo dato
            p[1] = valore - delta_3h


def imposta_allerta(st, giorno, **colori):
    st["allerte"][giorno]["colori"].update(colori)


def test_stato_soglia1_giallo(stato, cfg):
    imposta_livello(stato, "leo", 1.1)
    w = widget(stato, cfg)
    assert (w["stato"], w["stato_livello"], w["stato_colore"]) == ("Attenzione: Leo sopra soglia 1", 1, "#FBC02D")
    assert (w["leo_soglia"], w["leo_colore"]) == ("soglia 1", "#FBC02D")


def test_stato_soglia3_rosso(stato, cfg):
    imposta_livello(stato, "leo", 2.1)
    w = widget(stato, cfg)
    assert (w["stato"], w["stato_livello"], w["stato_colore"]) == ("ALLARME: Leo sopra soglia 3", 3, "#D32F2F")


def test_stato_livello_piu_alto_vince(stato, cfg):
    imposta_livello(stato, "leo", 1.1)
    imposta_livello(stato, "panaro", 3.0)
    w = widget(stato, cfg)
    assert (w["stato"], w["stato_livello"]) == ("Attenzione: Panaro sopra soglia 2", 2)
    assert "Leo sopra soglia 1" in w["stato_dettaglio"]


def test_stato_allerta_arancione_idraulica(stato, cfg):
    imposta_allerta(stato, "2026-11-06", idraulica="orange", temporali="yellow")
    w = widget(stato, cfg)
    assert (w["stato"], w["stato_livello"]) == ("Attenzione: Allerta arancione zona E1", 2)
    assert (w["allerta_oggi"], w["allerta_oggi_colore"]) == ("arancione", "#F57C00")
    assert w["allerta_oggi_eventi"] == "idraulica arancione, temporali gialla"


def test_allerta_vento_non_entra_nello_stato(stato, cfg):
    imposta_allerta(stato, "2026-11-06", vento="orange")
    w = widget(stato, cfg)
    assert w["allerta_oggi"] == "arancione"
    assert w["stato"] == "Tutto regolare"


def test_stato_in_crescita(stato, cfg):
    imposta_livello(stato, "leo", -0.30, delta_3h=0.15)
    w = widget(stato, cfg)
    assert (w["leo_tendenza"], w["leo_freccia"], w["leo_delta3h"]) == ("su", "↑", "+0.15 m")
    assert (w["stato"], w["stato_livello"]) == ("Attenzione: Leo in crescita", 1)


def test_a_parita_di_livello_vince_la_prima_regola(stato, cfg):
    imposta_livello(stato, "leo", 1.1, delta_3h=0.3)      # soglia 1 (regola 1) + crescita (regola 3)
    imposta_allerta(stato, "2026-11-06", temporali="yellow")   # allerta gialla (regola 2)
    w = widget(stato, cfg)
    assert w["stato"] == "Attenzione: Leo sopra soglia 1"
    assert w["stato_dettaglio"] == "Leo sopra soglia 1; Allerta gialla zona E1; Leo in crescita"


def test_stato_pioggia_osservata_abbondante(stato, cfg):
    stato["serie"]["pioggia_pratignano"][-2][1] += 30.0
    w = widget(stato, cfg)
    assert w["stato"] == "Attenzione: Pioggia abbondante ultime 24h (Pratignano 34 mm)"


def test_stato_pioggia_prevista_abbondante(stato, cfg):
    stato["previsione"]["giorni"][1].update(prec_min=20.0, prec_max=35.0)
    w = widget(stato, cfg)
    assert w["prev_domani"] == "20-35 mm"
    assert w["stato"] == "Attenzione: Pioggia abbondante prevista domani (20-35 mm)"


def test_stato_dati_non_aggiornati(stato, cfg):
    w = widget(stato, cfg, now=NOW + timedelta(days=2))
    assert all(w[k] for k in ("leo_vecchio", "panaro_vecchio", "pratignano_vecchio", "scaffaiolo_vecchio",
                              "prev_vecchio", "allerta_vecchio"))
    assert (w["stato"], w["stato_livello"], w["stato_colore"]) == ("Dati non aggiornati", -1, "#9E9E9E")


def test_dato_vecchio_dopo_2_ore(stato, cfg):
    assert widget(stato, cfg, now=NOW + timedelta(hours=1, minutes=17))["leo_vecchio"] is False   # dato 10:00Z, 1h59'
    w = widget(stato, cfg, now=NOW + timedelta(hours=1, minutes=19))                                # 2h01'
    assert w["leo_vecchio"] is True and w["pratignano_vecchio"] is True
    assert w["prev_vecchio"] is False and w["allerta_vecchio"] is False
