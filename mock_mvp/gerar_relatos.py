"""Gera relatos SIMULADOS para a área piloto (dado simulado com geração justificada e documentada).

Por que simular: o MVP ainda não tem usuários reais. Os relatos são sorteados ao longo das ciclovias
da Av. Paulista e da Av. Faria Lima (linha reta entre as pontas de cada ciclovia, com ruído de ~15 m).
De propósito, o arquivo inclui casos ruins para exercitar a automação:
  - 3 relatos duplicados (mesmo tipo a menos de 25 m de outro)
  - 1 relato sem coordenada, 1 com tipo inválido, 1 fora da cidade de São Paulo, 1 com severidade inválida
Semente fixa (42): rodar de novo gera exatamente o mesmo arquivo.

    python mock_mvp/gerar_relatos.py
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
CICLOVIAS = {  # (lat, lon) de início e fim aproximados
    "Av. Paulista": ((-23.5553, -46.6623), (-23.5703, -46.6447)),
    "Av. Brigadeiro Faria Lima": ((-23.5674, -46.6936), (-23.5925, -46.6789)),
}
TIPOS = ["buraco", "buraco", "buraco", "desnivel", "poca", "obstaculo"]
SEVERIDADES = ["baixa", "media", "media", "alta", "alta"]
ORIGENS = ["app", "app", "visao", "robo"]
agora = datetime(2026, 11, 18, 18, 0)

relatos = []
for i in range(1, 25):
    nome, ((la1, lo1), (la2, lo2)) = random.choice(list(CICLOVIAS.items()))
    f = random.random()
    relatos.append({
        "id": f"r{i:03d}",
        "lat": round(la1 + (la2 - la1) * f + random.uniform(-0.00012, 0.00012), 6),
        "lon": round(lo1 + (lo2 - lo1) * f + random.uniform(-0.00012, 0.00012), 6),
        "tipo": random.choice(TIPOS),
        "severidade": random.choice(SEVERIDADES),
        "origem": random.choice(ORIGENS),
        "data": (agora - timedelta(hours=random.randint(1, 240))).isoformat(timespec="minutes"),
        "simulado": True,
    })

# duplicados: cópia de 3 relatos deslocada ~5 m
for j, base in enumerate(relatos[:3], start=25):
    relatos.append(base | {"id": f"r{j:03d}", "lat": round(base["lat"] + 0.00004, 6), "origem": "app"})

# casos inválidos (vão para a quarentena)
relatos += [
    {"id": "r028", "lat": None, "lon": None, "tipo": "buraco", "severidade": "alta", "origem": "app", "data": agora.isoformat(timespec="minutes"), "simulado": True},
    {"id": "r029", "lat": -23.5612, "lon": -46.6560, "tipo": "jacare", "severidade": "alta", "origem": "app", "data": agora.isoformat(timespec="minutes"), "simulado": True},
    {"id": "r030", "lat": -22.9068, "lon": -43.1729, "tipo": "buraco", "severidade": "alta", "origem": "app", "data": agora.isoformat(timespec="minutes"), "simulado": True},
    {"id": "r031", "lat": -23.5790, "lon": -46.6870, "tipo": "buraco", "severidade": "altissima", "origem": "robo", "data": agora.isoformat(timespec="minutes"), "simulado": True},
]

destino = Path(__file__).with_name("relatos_seed.json")
destino.write_text(json.dumps(relatos, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(relatos)} relatos gravados em {destino}")
