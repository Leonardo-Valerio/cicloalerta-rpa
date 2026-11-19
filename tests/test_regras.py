"""Cenário de DECISÃO: a mesma regra com e sem chuva, e a validação dos dados."""
import pytest

from src.bot import carregar_config
from src.regras import decidir, deduplicar, validar

CFG = carregar_config()


@pytest.mark.parametrize("severidade, chuva, esperado", [
    ("alta", 5.0, "critico"),
    ("alta", 1.0, "critico"),     # exatamente no limiar conta como chuva
    ("alta", 0.9, None),          # abaixo do limiar: sem alerta
    ("alta", 0.0, None),          # mesmo relato sem chuva: sem alerta
    ("media", 3.0, "atencao"),
    ("baixa", 30.0, None),        # severidade baixa nunca gera alerta
])
def test_decisao_alerta(severidade, chuva, esperado):
    assert decidir(severidade, chuva, CFG["limiar_chuva_mm"]) == esperado


@pytest.mark.parametrize("relato, motivo", [
    ({"id": "a", "lat": None, "lon": None, "tipo": "buraco", "severidade": "alta"}, "sem_coordenada"),
    ({"id": "b", "lat": -22.90, "lon": -43.17, "tipo": "buraco", "severidade": "alta"}, "fora_de_sao_paulo"),
    ({"id": "c", "lat": -23.56, "lon": -46.65, "tipo": "jacare", "severidade": "alta"}, "tipo_invalido"),
    ({"id": "d", "lat": -23.56, "lon": -46.65, "tipo": "buraco", "severidade": "altissima"}, "severidade_invalida"),
    ({"id": "e", "lat": -23.56, "lon": -46.65, "tipo": "buraco", "severidade": "alta"}, None),
])
def test_validacao(relato, motivo):
    assert validar(relato, CFG) == motivo


def test_deduplicacao_une_mesmo_tipo_perto_e_mantem_o_mais_grave():
    rel = [
        {"id": "1", "lat": -23.56000, "lon": -46.65000, "tipo": "buraco", "severidade": "media", "data": "2026-11-01"},
        {"id": "2", "lat": -23.56004, "lon": -46.65000, "tipo": "buraco", "severidade": "alta", "data": "2026-11-02"},  # ~4 m
        {"id": "3", "lat": -23.56004, "lon": -46.65000, "tipo": "poca", "severidade": "alta", "data": "2026-11-02"},    # outro tipo
        {"id": "4", "lat": -23.57000, "lon": -46.65000, "tipo": "buraco", "severidade": "baixa", "data": "2026-11-02"}, # ~1 km
    ]
    unicos, dup = deduplicar(rel, 25)
    assert len(unicos) == 3 and [d["id"] for d in dup] == ["1"]
    buraco = next(u for u in unicos if u["id"] == "2")
    assert buraco["qtd_relatos"] == 2 and buraco["ids_unidos"] == ["2", "1"]
