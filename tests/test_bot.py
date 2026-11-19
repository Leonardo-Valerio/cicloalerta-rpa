"""Cenários de SUCESSO e FALHA do bot de ponta a ponta, com as fontes externas simuladas."""
import json

import pytest

from src import bot, clientes

RELATOS = [
    {"id": "r1", "lat": -23.5612, "lon": -46.6560, "tipo": "buraco", "severidade": "alta", "data": "2026-11-18T10:00"},
    {"id": "r2", "lat": -23.5790, "lon": -46.6870, "tipo": "desnivel", "severidade": "media", "data": "2026-11-18T10:00"},
    {"id": "r3", "lat": -23.5791, "lon": -46.6871, "tipo": "poca", "severidade": "baixa", "data": "2026-11-18T10:00"},
    {"id": "r4", "lat": -23.56121, "lon": -46.6560, "tipo": "buraco", "severidade": "media", "data": "2026-11-18T11:00"},  # duplicado de r1
    {"id": "r5", "lat": None, "lon": None, "tipo": "buraco", "severidade": "alta", "data": "2026-11-18T10:00"},          # inválido
]


@pytest.fixture
def cfg():
    c = bot.carregar_config()
    c["espera_inicial_s"] = 0  # testes sem espera real
    return c


@pytest.fixture
def pastas(tmp_path):
    bot.configurar_log(tmp_path / "logs")
    return tmp_path / "saida", tmp_path / "logs"


def test_sucesso_com_chuva(monkeypatch, cfg, pastas):
    publicados = []
    monkeypatch.setattr(clientes, "buscar_relatos", lambda c: [dict(r) for r in RELATOS])
    monkeypatch.setattr(clientes, "previsao_chuva", lambda c, cel: (4.2, False))
    monkeypatch.setattr(clientes, "publicar_alertas", lambda c, a: publicados.extend(a) or {"novos": len(a)})

    r = bot.executar(cfg, *pastas)

    assert r["status"] == "sucesso"
    assert (r["lidos"], r["quarentena"], r["duplicados"]) == (5, 1, 1)
    assert (r["alertas_critico"], r["alertas_atencao"]) == (1, 1)
    assert {a["relato_id"]: a["nivel"] for a in publicados} == {"r1": "critico", "r2": "atencao"}
    arq = next(pastas[0].glob("alertas_*.json"))
    assert len(json.loads(arq.read_text(encoding="utf-8"))) == 2


def test_decisao_mesmo_relato_sem_chuva_nao_gera_alerta(monkeypatch, cfg, pastas):
    monkeypatch.setattr(clientes, "buscar_relatos", lambda c: [dict(r) for r in RELATOS])
    monkeypatch.setattr(clientes, "previsao_chuva", lambda c, cel: (0.0, False))
    monkeypatch.setattr(clientes, "publicar_alertas", lambda c, a: pytest.fail("não deveria publicar"))

    r = bot.executar(cfg, *pastas)

    assert r["status"] == "sucesso" and r["alertas_critico"] == r["alertas_atencao"] == 0


def test_falha_api_do_mvp_fora_do_ar(monkeypatch, cfg, pastas):
    tentativas = []

    def api_fora(*a, **k):
        tentativas.append(1)
        raise clientes.requests.ConnectionError("recusada")

    monkeypatch.setattr(clientes.requests, "get", api_fora)
    r = bot.executar(cfg, *pastas)

    assert r["status"] == "falha" and len(tentativas) == cfg["tentativas"]
    assert bot.CODIGO[r["status"]] == 1
    log = next(pastas[1].glob("bot_*.log")).read_text(encoding="utf-8")
    assert "FALHA" in log and "indisponível após 3 tentativas" in log
    ultima = json.loads((pastas[1] / "execucoes.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert ultima["status"] == "falha"


def test_open_meteo_fora_usa_previsao_salva(monkeypatch, cfg, tmp_path):
    monkeypatch.setattr(clientes, "CACHE_CLIMA", tmp_path / "cache.json")
    (tmp_path / "cache.json").write_text(json.dumps({"-23.56,-46.66": {"mm": 2.5, "em": "2026-11-18T09:00"}}))
    monkeypatch.setattr(clientes.requests, "get", lambda *a, **k: (_ for _ in ()).throw(clientes.requests.Timeout()))
    cfg["espera_inicial_s"] = 0
    assert clientes.previsao_chuva(cfg, "-23.56,-46.66") == (2.5, True)


def test_publicacao_falha_vira_sucesso_parcial(monkeypatch, cfg, pastas):
    monkeypatch.setattr(clientes, "buscar_relatos", lambda c: [dict(r) for r in RELATOS])
    monkeypatch.setattr(clientes, "previsao_chuva", lambda c, cel: (4.2, False))

    def post_fora(c, a):
        raise clientes.FonteIndisponivel("API do MVP (POST /api/alertas) indisponível")

    monkeypatch.setattr(clientes, "publicar_alertas", post_fora)
    r = bot.executar(cfg, *pastas)
    assert r["status"] == "parcial" and bot.CODIGO["parcial"] == 2
    assert next(pastas[0].glob("alertas_*.json")).exists()  # integração por arquivo continua valendo
