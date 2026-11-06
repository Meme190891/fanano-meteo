"""Diagnostica di raggiungibilita' degli endpoint Arpae.

Esegue UNA richiesta per ciascun endpoint di produzione (gli stessi URL di fanano.arpae)
piu' due fonti solo diagnostiche, e stampa stato HTTP, dimensione, tempo e un controllo
del contenuto fatto con i parser veri. Da lanciare a mano (workflow "probe" o in locale):

    python -m fanano.probe

Exit code 1 se almeno un endpoint di produzione fallisce.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime

import requests

from fanano import arpae
from fanano.config import load_config

DIAGNOSTICI = {
    "diag open data realtime.jsonl": "https://dati-simc.arpae.it/opendata/osservati/meteo/realtime/realtime.jsonl",
    "diag dati.arpae.it": "https://dati.arpae.it/",
}


def _fmt(t: datetime) -> str:
    return t.astimezone(arpae.ROME).strftime("%d/%m %H:%M")


def valida(nome: str, resp: requests.Response, cfg: dict) -> str:
    """Controllo minimo del contenuto usando i parser di produzione."""
    if nome == "livelli":
        ids = {t["id"] for t in cfg["torrenti"]}
        found = arpae.parse_livelli(resp.json(), ids)
        if not found:
            raise ValueError("nessuna delle stazioni configurate trovata")
        return "; ".join(f"{s.nome}={s.valore} (soglie {s.soglia1}/{s.soglia2}/{s.soglia3})" for s in found.values())
    if nome.startswith(("livello_", "pioggia_")):
        serie = arpae.parse_serie(resp.json())
        if not serie:
            raise ValueError("serie vuota")
        return f"{len(serie)} punti, {_fmt(serie[0][0])} -> {_fmt(serie[-1][0])}, ultimo v={serie[-1][1]}"
    if nome.startswith("allerta_"):
        a = arpae.parse_allerta(resp.json(), cfg["zona_allerta"])
        if a is None:
            return "nessun documento (normale per domani prima dell'emissione)"
        return f"{a.titolo[:70]} | {a.zona}: {a.colori}"
    if nome == "previsione":
        giorni = arpae.parse_previsione(resp.text, cfg["previsione"]["zona"])
        return "; ".join(f"{g.giorno} {g.prec_testo} mm" for g in giorni)
    return f"Last-Modified: {resp.headers.get('last-modified')}"


def run(cfg: dict) -> list[dict]:
    session = arpae.make_session(cfg)
    timeout = cfg["arpae"].get("timeout_s", 20)
    controlli = [(n, u, True) for n, u in arpae.endpoint_urls(cfg).items()]
    controlli += [(n, u, False) for n, u in DIAGNOSTICI.items()]
    results = []
    for nome, url, produzione in controlli:
        t0 = time.monotonic()
        row = {"name": nome, "production": produzione, "url": url, "status": "-", "bytes": 0}
        try:
            # niente nuovo tentativo: vogliamo vedere il comportamento grezzo
            resp = session.get(url, timeout=timeout, stream=not produzione)
            row["status"] = resp.status_code
            if produzione:
                row["bytes"] = len(resp.content)
            resp.raise_for_status()
            row["detail"] = valida(nome, resp, cfg) if produzione else valida("diag", resp, cfg)
            row["ok"] = True
            resp.close()
        except Exception as exc:  # noqa: BLE001 - diagnostica: riportiamo qualsiasi errore
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
             f"Eseguito: {datetime.now(arpae.ROME):%d/%m/%Y %H:%M} (Europe/Rome)", "",
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
