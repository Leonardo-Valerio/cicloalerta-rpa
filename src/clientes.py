"""Acesso às fontes externas, sempre com repetição e espera crescente (sem falha silenciosa)."""
import json
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger("bot")
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
CACHE_CLIMA = Path(__file__).resolve().parent.parent / "dados" / "ultima_previsao.json"


class FonteIndisponivel(Exception):
    pass


def com_tentativas(nome: str, fn, tentativas: int, espera_s: float):
    for n in range(1, tentativas + 1):
        try:
            return fn()
        except (requests.RequestException, ValueError) as e:
            log.warning("%s: tentativa %d/%d falhou (%s)", nome, n, tentativas, type(e).__name__)
            if n < tentativas:
                time.sleep(espera_s * 2 ** (n - 1))
    raise FonteIndisponivel(f"{nome} indisponível após {tentativas} tentativas")


def buscar_relatos(cfg: dict) -> list[dict]:
    def chamar():
        r = requests.get(f"{cfg['mvp_url']}/api/relatos", timeout=cfg["timeout_s"])
        r.raise_for_status()
        dados = r.json()
        if not isinstance(dados, list):
            raise ValueError("resposta de /api/relatos não é uma lista")
        return dados
    return com_tentativas("API do MVP (GET /api/relatos)", chamar, cfg["tentativas"], cfg["espera_inicial_s"])


def publicar_alertas(cfg: dict, alertas: list[dict]) -> dict:
    def chamar():
        r = requests.post(f"{cfg['mvp_url']}/api/alertas", json=alertas, timeout=cfg["timeout_s"])
        r.raise_for_status()
        return r.json()
    return com_tentativas("API do MVP (POST /api/alertas)", chamar, cfg["tentativas"], cfg["espera_inicial_s"])


def _ler_cache() -> dict:
    try:
        return json.loads(CACHE_CLIMA.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def previsao_chuva(cfg: dict, celula: str) -> tuple[float, bool]:
    """Maior chuva prevista (mm) nas próximas horas para a célula.

    Devolve (mm, previsao_antiga). Se o Open-Meteo falhar, usa a última previsão salva e marca
    previsao_antiga=True. Sem previsão salva, levanta FonteIndisponivel.
    """
    lat, lon = map(float, celula.split(","))

    def chamar():
        r = requests.get(OPEN_METEO, timeout=cfg["timeout_s"], params={
            "latitude": lat, "longitude": lon, "hourly": "precipitation",
            "forecast_hours": cfg["horas_previsao"], "timezone": "America/Sao_Paulo"})
        r.raise_for_status()
        valores = [v for v in r.json()["hourly"]["precipitation"] if v is not None]
        if not valores:
            raise ValueError("Open-Meteo sem dados de precipitação")
        return max(valores)

    try:
        mm = com_tentativas("Open-Meteo", chamar, cfg["tentativas"], cfg["espera_inicial_s"])
        cache = _ler_cache()
        cache[celula] = {"mm": mm, "em": time.strftime("%Y-%m-%dT%H:%M")}
        CACHE_CLIMA.parent.mkdir(exist_ok=True)
        CACHE_CLIMA.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        return mm, False
    except FonteIndisponivel:
        antigo = _ler_cache().get(celula)
        if antigo is None:
            raise
        log.warning("Open-Meteo fora do ar: usando previsão salva de %s para a célula %s", antigo["em"], celula)
        return antigo["mm"], True
