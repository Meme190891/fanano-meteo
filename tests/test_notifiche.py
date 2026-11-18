"""Notifiche Telegram: inizio/fine degli eventi, nessuna ripetizione, invio fallito, token mai esposto."""

from datetime import datetime, timedelta, timezone

import pytest
import requests

from fanano import compute, main, notifiche
from conftest import FIX, NOW

UTC = timezone.utc


def _st(now, leo=(), prat=(), scaff=(), allerte=None):
    """Stato sintetico: leo = livelli ogni 15' fino a `now`; prat/scaff = mm orari fino a `now`."""
    st = compute.stato_vuoto()
    fine = now.replace(minute=0, second=0, microsecond=0)
    st["serie"]["livello_leo"] = [[(fine - timedelta(minutes=15 * (len(leo) - 1 - i))).isoformat(), v]
                                  for i, v in enumerate(leo)]
    for nome, vals in (("pioggia_pratignano", prat), ("pioggia_scaffaiolo", scaff)):
        st["serie"][nome] = [[(fine - timedelta(hours=len(vals) - 1 - i)).isoformat(), v]
                             for i, v in enumerate(vals)]
    st["allerte"] = allerte or {}
    return st


def _piatto(n=16, v=-0.45):
    return [v] * n


class Posta:
    def __init__(self, guasta=False):
        self.inviati, self.guasta = [], guasta

    def __call__(self, testo):
        if self.guasta:
            raise RuntimeError("Telegram HTTP 401 Unauthorized")
        self.inviati.append(testo)


def _giro(st, cfg, now, posta):
    err = notifiche.gestisci(st, cfg, now, posta)
    return err, (posta.inviati[-1] if posta.inviati else None)


def test_senza_segreti_non_fa_nulla(cfg, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    assert notifiche.mittente_da_ambiente() is None
    st = _st(NOW, leo=_piatto(), prat=[9.0] * 4)
    assert notifiche.gestisci(st, cfg, NOW, None) == [] and st["notifiche"] is None


def test_primo_messaggio_e_riepilogo(cfg):
    st, posta = _st(NOW, leo=_piatto(), prat=[0.0] * 4, scaff=[0.0] * 4), Posta()
    _giro(st, cfg, NOW, posta)
    assert posta.inviati[0].startswith("✅ Notifiche meteo Fanano attive. Al momento nessun evento")
    assert st["notifiche"]["attivi"] == {}
    _giro(st, cfg, NOW + timedelta(minutes=30), posta)     # nulla di nuovo: nessun messaggio
    assert len(posta.inviati) == 1


def test_leo_salita_inizio_e_fine(cfg):
    posta = Posta()
    st = _st(NOW, leo=_piatto(), prat=[0.0] * 4, scaff=[0.0] * 4)
    _giro(st, cfg, NOW, posta)
    # sale di 15 cm in 3 ore
    t1 = NOW + timedelta(hours=1)
    st["serie"] = _st(t1, leo=_piatto(12) + [-0.40, -0.36, -0.33, -0.30], prat=[0.0] * 4, scaff=[0.0] * 4)["serie"]
    _, msg = _giro(st, cfg, t1, posta)
    assert "Leo in crescita: −0.30 m" in msg and "+15 cm nelle ultime 3 ore" in msg
    assert "index.html" in msg and len(posta.inviati) == 2
    # continua a salire: nessun nuovo messaggio, ma il massimo viene aggiornato
    t2 = t1 + timedelta(hours=1)
    st["serie"] = _st(t2, leo=_piatto(8) + [-0.40, -0.36, -0.33, -0.30, -0.26, -0.22, -0.20, -0.19],
                      prat=[0.0] * 4, scaff=[0.0] * 4)["serie"]
    _giro(st, cfg, t2, posta)
    assert len(posta.inviati) == 2 and st["notifiche"]["attivi"]["leo_salita"]["max"] == -0.19
    # si ferma
    t3 = t2 + timedelta(hours=4)
    st["serie"] = _st(t3, leo=[-0.19] + [-0.21] * 15, prat=[0.0] * 4, scaff=[0.0] * 4)["serie"]
    _, msg = _giro(st, cfg, t3, posta)
    assert "ha smesso di salire" in msg and "massimo −0.19 m" in msg and "era −0.45 m" in msg
    assert "leo_salita" not in st["notifiche"]["attivi"]


def test_pioggia_forte_inizio_e_fine_con_totali(cfg):
    posta = Posta()
    st = _st(NOW, leo=_piatto(), prat=[0.0] * 4, scaff=[0.0] * 4)
    _giro(st, cfg, NOW, posta)
    t1 = NOW + timedelta(hours=1)
    st["serie"] = _st(t1, leo=_piatto(), prat=[0.0, 0.0, 2.0, 6.4], scaff=[0.0, 1.0, 3.0, 8.2])["serie"]
    _, msg = _giro(st, cfg, t1, posta)
    assert "Pioggia forte a Scaffaiolo: 8.2 mm" in msg and "anche Pratignano 6.4 mm" in msg
    t2 = t1 + timedelta(hours=2)                       # ultima ora forte 2 ore fa: ancora in corso
    st["serie"] = _st(t2, leo=_piatto(), prat=[0.0, 0.0, 2.0, 6.4, 1.0, 0.5],
                      scaff=[0.0, 1.0, 3.0, 8.2, 2.0, 0.0])["serie"]
    _giro(st, cfg, t2, posta)
    assert len(posta.inviati) == 2
    t3 = t1 + timedelta(hours=3)
    st["serie"] = _st(t3, leo=_piatto(), prat=[0.0, 0.0, 2.0, 6.4, 1.0, 0.5, 0.0],
                      scaff=[0.0, 1.0, 3.0, 8.2, 2.0, 0.0, 0.0])["serie"]
    _, msg = _giro(st, cfg, t3, posta)
    assert "Pioggia forte terminata" in msg
    assert "Pratignano 7.9 mm" in msg and "Scaffaiolo 10.2 mm" in msg


def _doc(giorno, colori):
    return {"inizio": f"{giorno}T00:00:00+01:00", "fine": "x", "colori": colori}


def test_allerta_nuova_cambiata_e_terminata(cfg):
    posta = Posta()
    oggi, domani = "2026-11-06", "2026-11-07"
    verde = {"idraulica": "green", "neve": "green"}
    st = _st(NOW, leo=_piatto(), allerte={oggi: _doc(oggi, verde)})
    _giro(st, cfg, NOW, posta)
    st["allerte"][domani] = _doc(domani, {"idrogeologica": "yellow", "neve": "yellow", "vento": "green"})
    _, msg = _giro(st, cfg, NOW, posta)
    assert msg.startswith("⚠️ Allerta gialla zona E1 domani: idrogeologica, neve.")
    _giro(st, cfg, NOW + timedelta(minutes=30), posta)             # stesso bollettino: niente
    assert len(posta.inviati) == 2
    st["allerte"][domani] = _doc(domani, {"idrogeologica": "red"})
    _, msg = _giro(st, cfg, NOW, posta)
    assert msg.startswith("🚨 Allerta rossa zona E1 domani (cambiata): idrogeologica.")
    # il giorno dopo l'allerta di "domani" diventa "oggi": nessuna ripetizione
    t = NOW + timedelta(days=1)
    st["serie"] = _st(t, leo=_piatto())["serie"]
    _giro(st, cfg, t, posta)
    assert len(posta.inviati) == 3
    st["allerte"] = {domani: _doc(domani, verde)}
    _, msg = _giro(st, cfg, t, posta)
    assert "Allerta zona E1 terminata" in msg and st["notifiche"]["attivi"] == {}


def test_guasto_e_ripresa_senza_falsa_fine_eventi(cfg):
    posta = Posta()
    st = _st(NOW, leo=_piatto(12) + [-0.40, -0.35, -0.30, -0.25])
    _giro(st, cfg, NOW, posta)
    assert "In corso adesso" in posta.inviati[0] and "Leo in crescita" in posta.inviati[0]
    tardi = NOW + timedelta(hours=4)                           # nessun dato nuovo da 4 ore
    _, msg = _giro(st, cfg, tardi, posta)
    assert msg.startswith("🔧 Dati Arpae non aggiornati dalle")
    assert "leo_salita" in st["notifiche"]["attivi"]           # non dichiarata finita a dati fermi
    _giro(st, cfg, tardi + timedelta(minutes=30), posta)       # nessuna ripetizione
    assert len(posta.inviati) == 2
    st["serie"] = _st(tardi, leo=[-0.25] * 16)["serie"]
    _, msg = _giro(st, cfg, tardi, posta)
    assert "Dati Arpae di nuovo aggiornati" in msg and "ha smesso di salire" in msg


def test_invio_fallito_stato_non_avanza(cfg):
    st = _st(NOW, leo=_piatto())
    err = notifiche.gestisci(st, cfg, NOW, Posta(guasta=True))
    assert err == ["notifiche: Telegram HTTP 401 Unauthorized"] and st["notifiche"] is None


def test_prova_notifica(cfg):
    st, posta = _st(NOW, leo=_piatto()), Posta()
    notifiche.gestisci(st, cfg, NOW, posta)
    notifiche.gestisci(st, cfg, NOW, posta, prova=True)
    assert posta.inviati[-1].startswith("🔔 Messaggio di prova")


def test_token_mai_negli_errori(monkeypatch):
    def rete_giu(url, **kw):
        raise requests.ConnectionError(f"fallita connessione a {url}")
    monkeypatch.setattr(notifiche.requests, "post", rete_giu)
    with pytest.raises(RuntimeError) as e:
        notifiche.invia_telegram("ciao", "123:SEGRETO", "42")
    assert "SEGRETO" not in str(e.value) and e.value.__cause__ is None


def test_esegui_con_notifiche(cfg, tmp_path):
    posta = Posta()
    w = main.esegui(cfg, tmp_path, tmp_path / "state.json", main.raccogli_da_cartella(FIX, cfg, NOW), NOW,
                    grafici=False, invia=posta)
    assert w["errori"] == "" and len(posta.inviati) == 1
    assert compute.stato_vuoto()["notifiche"] is None
    stato = main.leggi_stato(tmp_path / "state.json")
    assert stato["notifiche"]["aggiornato"] == NOW.isoformat()
