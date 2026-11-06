"""Diagnostica di raggiungibilita' degli endpoint Arpae.

Esegue UNA richiesta per ciascun endpoint usato in produzione (piu' due fonti
diagnostiche) e stampa stato HTTP, dimensione, tempo e un controllo minimo sul
contenuto. Da lanciare a mano (workflow "probe" su GitHub o in locale):

    python -m fanano.probe

Exit code 1 se almeno un endpoint di produzione fallisce.
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import requests
import yaml

ROME = ZoneInfo("Europe/Rome")
ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Check:
    name: str
    url: str
    validate: Callable[[requests.Response], str]
    production: bool = True
    method: str = "GET"


def load_config(path: Path = ROOT / "config.yaml") -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _fmt_ms(t_ms: int) -> str:
    return datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).astimezone(ROME).strftime("%d/%m %H:%M")


def _series_summary(resp: requests.Response) -> str:
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise ValueError("serie vuota o non e' una lista")
    first, last = data[0], data[-1]
    return f"{len(data)} punti, {_fmt_ms(int(first['t']))} -> {_fmt_ms(int(last['t']))}, ultimo v={last['v']}"


def build_checks(cfg: dict) -> list[Check]:
    base = cfg["arpae"]["base_url"].rstrip("/")
    var_liv = cfg["variabili"]["livello"]
    var_pio = cfg["variabili"]["pioggia_oraria"]
    zona = cfg["zona_allerta"]
    prov = cfg["previsione"]["provincia"]
    idro_ids = {t["id"]: t["nome"] for t in cfg["torrenti"]}

    now = int(time.time())
    slot_ms = ((now // 1800) * 1800 - 1800) * 1000
    domani = (datetime.now(ROME) + timedelta(days=1)).strftime("%Y-%m-%d")

    def v_livelli(resp: requests.Response) -> str:
        data = resp.json()
        found = {s["idstazione"]: s for s in data if isinstance(s, dict) and s.get("idstazione") in idro_ids}
        if not found:
            raise ValueError("nessuna delle stazioni configurate trovata")
        parts = [
            f"{s['nomestaz']}={s.get('value')} (soglie {s.get('soglia1')}/{s.get('soglia2')}/{s.get('soglia3')})"
            for s in found.values()
        ]
        return f"{len(data)} stazioni; " + "; ".join(parts)

    def v_allerta(resp: requests.Response) -> str:
        data = resp.json()
        if not data:  # {} o []: documento non (ancora) emesso
            return "nessun documento (normale per domani prima dell'emissione)"
        if not isinstance(data, dict):
            raise ValueError("risposta non e' un oggetto JSON")
        if not data.get("titolo"):
            return "nessun documento (normale per domani prima dell'emissione)"
        zone = data.get(zona) or {}
        colori = {k: v for k, v in zone.items() if v and k != "nome"}
        return f"{data['titolo'][:70]}... | {zona}: {colori}"

    def v_previsione(resp: requests.Response) -> str:
        html = resp.text
        n_tab = html.count("table--previsioni")
        prec = re.findall(r">Prec</abbr>\s*</th>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>", html)
        if not n_tab or not prec:
            raise ValueError("tabelle di previsione non trovate (struttura HTML cambiata?)")
        return f"{n_tab} tabelle; Prec rilievi/pianura per giorno: {prec}"

    def v_realtime_head(resp: requests.Response) -> str:
        return f"Last-Modified: {resp.headers.get('last-modified')}, {resp.headers.get('content-length')} B"

    def v_ckan(resp: requests.Response) -> str:
        data = resp.json()
        res = data.get("result", {})
        urls = [r.get("url") for r in res.get("resources", [])]
        return f"success={data.get('success')}, licenza={res.get('license_id')}, risorse={urls}"

    checks = [
        Check("E1 livelli+soglie",
              f"{base}/o/api/allerta/get-sensor-values?variabile={var_liv}&time={slot_ms}", v_livelli),
    ]
    for t in cfg["torrenti"]:
        checks.append(Check(f"E2 serie livello {t['chiave']} ({t['id']})",
                            f"{base}/o/api/allerta/get-time-series/?stazione={t['id']}&variabile={var_liv}",
                            _series_summary))
    for p in cfg["pluviometri"]:
        checks.append(Check(f"E3 serie pioggia {p['chiave']} ({p['id']})",
                            f"{base}/o/api/allerta/get-time-series/?stazione={p['id']}&variabile={var_pio}",
                            _series_summary))
    checks += [
        Check("E4 stato allerta oggi", f"{base}/o/get-stato-allerta", v_allerta),
        Check("E4 stato allerta domani", f"{base}/o/get-stato-allerta?data={domani}%2012:00", v_allerta),
        Check(f"E5 previsione provincia {prov}",
              f"{base}/previsioni-regionali?p_p_id=AllertaPrevisioniTerritorioPortlet&p_p_lifecycle=0"
              f"&p_p_state=normal&p_p_mode=view&_AllertaPrevisioniTerritorioPortlet_prov={prov}",
              v_previsione),
        # Fonti solo diagnostiche (non usate in produzione)
        Check("diag open data realtime.jsonl (HEAD)",
              "https://dati-simc.arpae.it/opendata/osservati/meteo/realtime/realtime.jsonl",
              v_realtime_head, production=False, method="HEAD"),
        Check("diag dati.arpae.it CKAN bollettino",
              "https://dati.arpae.it/api/3/action/package_show?id=bollettino-testuale-previsioni-meteo",
              v_ckan, production=False),
    ]
    return checks


def run(cfg: dict) -> list[dict]:
    session = requests.Session()
    session.headers["User-Agent"] = cfg["arpae"]["user_agent"]
    timeout = cfg["arpae"].get("timeout_s", 20)
    results = []
    for chk in build_checks(cfg):
        t0 = time.monotonic()
        row = {"name": chk.name, "production": chk.production, "url": chk.url}
        try:
            resp = session.request(chk.method, chk.url, timeout=timeout)
            row["status"] = resp.status_code
            row["bytes"] = len(resp.content)
            resp.raise_for_status()
            row["detail"] = chk.validate(resp)
            row["ok"] = True
        except Exception as exc:  # noqa: BLE001 - diagnostica: riportiamo qualsiasi errore
            row.setdefault("status", "-")
            row.setdefault("bytes", 0)
            row["detail"] = f"{type(exc).__name__}: {exc}"[:300]
            row["ok"] = False
        row["ms"] = int((time.monotonic() - t0) * 1000)
        results.append(row)
        print(f"[{'OK ' if row['ok'] else 'ERR'}] {row['name']}: HTTP {row['status']}, "
              f"{row['bytes']} B, {row['ms']} ms -> {row['detail']}", flush=True)
    return results


def write_summary(results: list[dict]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = ["## Probe endpoint Arpae", "",
             f"Eseguito: {datetime.now(ROME):%d/%m/%Y %H:%M} (Europe/Rome)", "",
             "| Esito | Endpoint | Prod. | HTTP | Byte | ms | Dettaglio |",
             "|---|---|---|---|---|---|---|"]
    for r in results:
        detail = str(r["detail"]).replace("|", "\\|")
        lines.append(f"| {'✅' if r['ok'] else '❌'} | {r['name']} | {'sì' if r['production'] else 'no'} "
                     f"| {r['status']} | {r['bytes']} | {r['ms']} | {detail} |")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    results = run(load_config())
    write_summary(results)
    failed = [r["name"] for r in results if r["production"] and not r["ok"]]
    if failed:
        print(f"\nEndpoint di produzione falliti: {failed}", file=sys.stderr)
        return 1
    print("\nTutti gli endpoint di produzione rispondono.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
