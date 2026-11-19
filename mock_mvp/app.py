"""MVP local do CicloAlerta: implementa o contrato da API usado pelo bot (relatos e alertas)
e um mapa simples. Serve para desenvolver e demonstrar sem depender da URL pública do grupo.

    uvicorn mock_mvp.app:app --port 8000      (de dentro da pasta rpa/)
    abrir http://localhost:8000

O estado fica em mock_mvp/estado.json. Para recomeçar do zero, apague esse arquivo.
"""
import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

PASTA = Path(__file__).parent
ESTADO = PASTA / "estado.json"


def carregar() -> dict:
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    seed = json.loads((PASTA / "relatos_seed.json").read_text(encoding="utf-8"))
    return {"relatos": seed, "alertas": []}


def salvar(d: dict):
    ESTADO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


app = FastAPI(title="CicloAlerta · MVP local")


class Relato(BaseModel):
    lat: float
    lon: float
    tipo: str
    severidade: str
    origem: str = "app"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/relatos")
def listar_relatos():
    return carregar()["relatos"]


@app.post("/api/relatos", status_code=201)
def criar_relato(r: Relato):
    d = carregar()
    novo = r.model_dump() | {"id": f"r{len(d['relatos']) + 1:03d}", "data": datetime.now().isoformat(timespec="minutes")}
    d["relatos"].append(novo)
    salvar(d)
    return novo


@app.get("/api/alertas")
def listar_alertas():
    agora = datetime.now().isoformat(timespec="minutes")
    return [a for a in carregar()["alertas"] if a.get("valido_ate", "9999") >= agora]


@app.post("/api/alertas")
def publicar_alertas(alertas: list[dict]):
    """Upsert pelo id do alerta: reenviar o mesmo lote não duplica nada (idempotente)."""
    d = carregar()
    por_id = {a["id"]: a for a in d["alertas"]}
    novos = sum(1 for a in alertas if a["id"] not in por_id)
    por_id.update({a["id"]: a for a in alertas})
    d["alertas"] = list(por_id.values())
    salvar(d)
    return {"recebidos": len(alertas), "novos": novos, "total": len(d["alertas"])}


@app.get("/", response_class=HTMLResponse)
def mapa():
    return (PASTA / "mapa.html").read_text(encoding="utf-8")
