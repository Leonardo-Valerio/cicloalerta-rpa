"""Bot de triagem do CicloAlerta.

Fluxo: lê os relatos do MVP -> valida (inválidos vão para quarentena) -> une duplicados ->
consulta a chuva prevista por região -> decide o nível de alerta de cada perigo ->
publica os alertas no MVP -> grava evidências (JSON, CSV para o SP156, log de auditoria).

    python -m src.bot                       # uma execução
    python -m src.bot --a-cada 60           # roda de hora em hora
    python -m src.bot --simular-chuva 5     # demonstração em dia seco (marcado nos alertas e no log)

Códigos de saída: 0 sucesso · 2 sucesso parcial (alertas salvos em arquivo, não publicados) · 1 falha.
"""
import argparse
import csv
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from . import clientes, regras

RAIZ = Path(__file__).resolve().parent.parent
log = logging.getLogger("bot")


def carregar_config(caminho: Path = RAIZ / "config.yaml") -> dict:
    cfg = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    cfg["mvp_url"] = os.getenv("MVP_URL", cfg["mvp_url"]).rstrip("/")
    return cfg


def configurar_log(pasta: Path) -> Path:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pasta.mkdir(exist_ok=True)
    arq = pasta / f"bot_{datetime.now():%Y-%m-%d}.log"
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    for h in (logging.FileHandler(arq, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)
    return arq


def id_alerta(relato_id: str, nivel: str, quando: datetime) -> str:
    """Mesmo perigo + mesmo nível + mesma janela de 3 h = mesmo id (reexecutar não duplica)."""
    janela = quando.replace(minute=0, second=0, microsecond=0, hour=quando.hour // 3 * 3)
    return hashlib.sha1(f"{relato_id}|{nivel}|{janela:%Y%m%d%H}".encode()).hexdigest()[:12]


def executar(cfg: dict, pasta_saida: Path = RAIZ / "saida", pasta_logs: Path = RAIZ / "logs",
             simular_chuva: float | None = None) -> dict:
    inicio = datetime.now()
    resumo = {"execucao": inicio.isoformat(timespec="seconds"), "lidos": 0, "validos": 0, "quarentena": 0,
              "duplicados": 0, "perigos": 0, "alertas_critico": 0, "alertas_atencao": 0,
              "sem_previsao": 0, "previsao_antiga": 0, "publicado": False, "status": "falha",
              "simulacao_chuva_mm": simular_chuva, "erros": []}
    pasta_saida.mkdir(exist_ok=True)
    log.info("Início da execução (MVP: %s)%s", cfg["mvp_url"],
             f" · MODO DEMONSTRAÇÃO: chuva simulada de {simular_chuva} mm" if simular_chuva is not None else "")

    # 1. Entrada
    try:
        relatos = clientes.buscar_relatos(cfg)
    except clientes.FonteIndisponivel as e:
        log.error("FALHA: %s. Nenhum alerta foi gerado nesta execução.", e)
        resumo["erros"].append(str(e))
        return _fechar(resumo, pasta_logs, inicio)
    resumo["lidos"] = len(relatos)
    log.info("Relatos lidos: %d", len(relatos))

    # 2. Validação (repetição sobre a coleção + decisão por item)
    validos, quarentena = [], []
    for r in relatos:
        motivo = regras.validar(r, cfg)
        if motivo:
            quarentena.append({"id": r.get("id"), "motivo": motivo})
            log.warning("Quarentena: relato %s (%s)", r.get("id"), motivo)
        else:
            validos.append(r)
    resumo["validos"], resumo["quarentena"] = len(validos), len(quarentena)

    # 3. Duplicados
    perigos, duplicados = regras.deduplicar(validos, cfg["raio_duplicado_m"])
    resumo["duplicados"], resumo["perigos"] = len(duplicados), len(perigos)
    for d in duplicados:
        log.info("Duplicado unido: relato %s", d["id"])

    # 4. Clima por região (uma consulta por célula de ~1 km)
    chuva: dict[str, tuple[float, bool]] = {}
    for cel in sorted({regras.celula(p) for p in perigos}):
        if simular_chuva is not None:
            chuva[cel] = (simular_chuva, False)
            continue
        try:
            chuva[cel] = clientes.previsao_chuva(cfg, cel)
        except clientes.FonteIndisponivel as e:
            log.error("Sem previsão para a célula %s: %s", cel, e)
            resumo["erros"].append(f"sem previsão para {cel}")

    # 5. Decisão por perigo
    alertas, consolidados = [], []
    for p in perigos:
        p["ciclovia"] = regras.ciclovia_de(p, cfg)
        prev = chuva.get(regras.celula(p))
        if prev is None:
            resumo["sem_previsao"] += 1
            nivel, mm, antiga = None, None, False
        else:
            mm, antiga = prev
            nivel = regras.decidir(p["severidade"], mm, cfg["limiar_chuva_mm"])
        consolidados.append({"perigo_id": p["id"], "ciclovia": p["ciclovia"], "tipo": p["tipo"],
                             "severidade": p["severidade"], "qtd_relatos": p["qtd_relatos"],
                             "lat": p["lat"], "lon": p["lon"], "chuva_prevista_mm": mm,
                             "alerta": nivel or "", "mapa": f"https://www.google.com/maps?q={p['lat']},{p['lon']}"})
        if nivel:
            alertas.append({"id": id_alerta(p["id"], nivel, inicio), "relato_id": p["id"], "nivel": nivel,
                            "tipo": p["tipo"], "severidade": p["severidade"], "ciclovia": p["ciclovia"],
                            "lat": p["lat"], "lon": p["lon"], "chuva_mm": mm, "previsao_antiga": antiga,
                            "simulado": simular_chuva is not None,
                            "criado_em": inicio.isoformat(timespec="minutes"),
                            "valido_ate": (inicio + timedelta(hours=cfg["validade_alerta_h"])).isoformat(timespec="minutes")})
            resumo["alertas_" + nivel] += 1
            resumo["previsao_antiga"] += int(antiga)
    log.info("Decisão: %d críticos, %d de atenção, %d sem alerta",
             resumo["alertas_critico"], resumo["alertas_atencao"], len(perigos) - len(alertas))

    # 6. Saídas estruturadas (integração por arquivo, sempre gravadas)
    dia = f"{inicio:%Y-%m-%d}"
    (pasta_saida / f"alertas_{dia}.json").write_text(json.dumps(alertas, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta_saida / f"quarentena_{dia}.json").write_text(json.dumps(quarentena, ensure_ascii=False, indent=1), encoding="utf-8")
    with (pasta_saida / f"perigos_consolidados_{dia}.csv").open("w", newline="", encoding="utf-8-sig") as f:
        if consolidados:
            w = csv.DictWriter(f, fieldnames=list(consolidados[0]), delimiter=";")
            w.writeheader()
            w.writerows(sorted(consolidados, key=lambda c: (c["alerta"] != "critico", c["alerta"] != "atencao")))

    # 7. Integração por API
    if alertas:
        try:
            ret = clientes.publicar_alertas(cfg, alertas)
            resumo["publicado"] = True
            log.info("Alertas publicados no MVP: %s", ret)
        except clientes.FonteIndisponivel as e:
            log.error("Alertas NÃO publicados (%s). Ficaram salvos em saida/alertas_%s.json", e, dia)
            resumo["erros"].append(str(e))
    else:
        resumo["publicado"] = True  # nada a publicar

    resumo["status"] = "sucesso" if resumo["publicado"] and not resumo["sem_previsao"] else "parcial"
    return _fechar(resumo, pasta_logs, inicio)


def _fechar(resumo: dict, pasta_logs: Path, inicio: datetime) -> dict:
    resumo["duracao_s"] = round((datetime.now() - inicio).total_seconds(), 2)
    pasta_logs.mkdir(exist_ok=True)
    with (pasta_logs / "execucoes.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(resumo, ensure_ascii=False) + "\n")
    log.info("Fim: status=%s · lidos=%d · válidos=%d · quarentena=%d · duplicados=%d · críticos=%d · atenção=%d · %.1f s",
             resumo["status"], resumo["lidos"], resumo["validos"], resumo["quarentena"], resumo["duplicados"],
             resumo["alertas_critico"], resumo["alertas_atencao"], resumo["duracao_s"])
    return resumo


CODIGO = {"sucesso": 0, "parcial": 2, "falha": 1}


def main():
    ap = argparse.ArgumentParser(description="Bot de triagem e alertas do CicloAlerta")
    ap.add_argument("--a-cada", type=int, metavar="MIN", help="repete a cada MIN minutos")
    ap.add_argument("--simular-chuva", type=float, metavar="MM", help="demonstração: usa esta chuva no lugar da previsão")
    a = ap.parse_args()
    configurar_log(RAIZ / "logs")
    cfg = carregar_config()
    while True:
        resumo = executar(cfg, simular_chuva=a.simular_chuva)
        if not a.a_cada:
            sys.exit(CODIGO[resumo["status"]])
        log.info("Próxima execução em %d min", a.a_cada)
        time.sleep(a.a_cada * 60)


if __name__ == "__main__":
    main()
