"""Regras de negócio do bot (funções puras, fáceis de testar)."""
from math import asin, cos, radians, sin, sqrt


def validar(relato: dict, cfg: dict) -> str | None:
    """Devolve o motivo da recusa, ou None se o relato é válido."""
    lat, lon = relato.get("lat"), relato.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return "sem_coordenada"
    a = cfg["area_sao_paulo"]
    if not (a["lat_min"] <= lat <= a["lat_max"] and a["lon_min"] <= lon <= a["lon_max"]):
        return "fora_de_sao_paulo"
    if relato.get("tipo") not in cfg["tipos_validos"]:
        return "tipo_invalido"
    if relato.get("severidade") not in cfg["severidades_validas"]:
        return "severidade_invalida"
    if not relato.get("id"):
        return "sem_id"
    return None


def distancia_m(a: dict, b: dict) -> float:
    """Distância em metros entre dois pontos (fórmula de haversine)."""
    la1, lo1, la2, lo2 = map(radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(h))


def deduplicar(relatos: list[dict], raio_m: float) -> tuple[list[dict], list[dict]]:
    """Une relatos do mesmo tipo a menos de `raio_m`. Fica o de maior severidade (empate: o mais antigo).

    Devolve (perigos_unicos, duplicados). Cada perigo único ganha `qtd_relatos` e `ids_unidos`.
    """
    peso = {"baixa": 0, "media": 1, "alta": 2}
    ordenados = sorted(relatos, key=lambda r: (-peso[r["severidade"]], r.get("data", "")))
    unicos, duplicados = [], []
    for r in ordenados:
        par = next((u for u in unicos if u["tipo"] == r["tipo"] and distancia_m(u, r) <= raio_m), None)
        if par:
            par["qtd_relatos"] += 1
            par["ids_unidos"].append(r["id"])
            duplicados.append(r)
        else:
            unicos.append(r | {"qtd_relatos": 1, "ids_unidos": [r["id"]]})
    return unicos, duplicados


def decidir(severidade: str, chuva_max_mm: float, limiar_mm: float) -> str | None:
    """Regra de decisão do alerta.

    alta  + chuva >= limiar -> "critico"
    media + chuva >= limiar -> "atencao"
    qualquer outro caso     -> None (sem alerta)
    """
    if chuva_max_mm < limiar_mm:
        return None
    return {"alta": "critico", "media": "atencao"}.get(severidade)


def ciclovia_de(relato: dict, cfg: dict) -> str:
    for c in cfg["ciclovias"]:
        if c["lat_min"] <= relato["lat"] <= c["lat_max"] and c["lon_min"] <= relato["lon"] <= c["lon_max"]:
            return c["nome"]
    return "fora da área piloto"


def celula(relato: dict) -> str:
    """Agrupa pontos em células de ~1 km para fazer uma só consulta de clima por região."""
    return f"{round(relato['lat'], 2)},{round(relato['lon'], 2)}"
