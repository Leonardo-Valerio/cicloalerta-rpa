# CicloAlerta · Automação (RPA): bot de triagem e alertas de chuva

> Global Solution 2026.2 · CitizenTech · Engenharia de Software 4º ano · disciplina **Robotic Process Automation**

## Integrantes

| Nome completo | RM |
| --- | --- |
| Breno Silva | RM97864 |
| Enrico Marquez | RM99325 |
| Gustavo Dias | RM550820 |
| Joel Barros | RM550378 |
| Leonardo Moreira | RM550988 |

## Ficha Técnica do MVP

| Campo | Conteúdo |
| --- | --- |
| Nome do produto | CicloAlerta |
| Cidadão e território | Ciclistas e entregadores de bicicleta elétrica nas ciclovias da cidade de São Paulo (área piloto: Av. Paulista e Av. Brigadeiro Faria Lima) |
| Problema, em uma frase | Buracos e desníveis nas ciclovias causam quedas, e na chuva ficam escondidos pela água |
| Proposta de valor | Saber antes de sair, e durante o trajeto, onde estão os trechos perigosos, com alerta mais forte em dia de chuva |
| Arquitetura: componentes | Site + API (FastAPI), detector de buracos (YOLO), assistente (LLM local com RAG e agente), pipeline de dados (Airflow + Databricks), **bot de triagem e alertas (Python, este repositório)**, robô com sensor (ESP32), publicado com Docker, Terraform e CI/CD |
| Fontes de dados | Open-Meteo (chuva), malha cicloviária do GeoSampa, relatos feitos no próprio MVP (parte simulada e documentada), legislação de trânsito |
| Modelos de IA utilizados | YOLO treinado para buracos; LLM local `qwen2.5:3b` via Ollama com busca semântica (`bge-m3`) |
| Repositório | https://github.com/Leonardo-Valerio/cicloalerta-rpa |
| Indicadores de impacto | Perigos mapeados, % de relatos confirmados, alertas enviados em dias de chuva, tempo até o perigo ser resolvido |
| ODS conectados | ODS 11 (meta 11.2, transporte seguro), ODS 3 (meta 3.6, menos lesões no trânsito), ODS 9 (meta 9.1, infraestrutura resiliente) |

**Vídeo de demonstração:** https://youtu.be/HWE1H6vYt8c

## O processo manual que este bot substitui

Sem o bot, alguém da operação precisaria, toda hora: abrir a lista de relatos de buracos, descartar os relatos
quebrados, juntar relatos repetidos do mesmo buraco, olhar a previsão do tempo de cada região, decidir quais trechos
ficam perigosos com a chuva, avisar os ciclistas e montar a lista de pedidos de conserto para o SP156.
O bot faz isso sozinho, de hora em hora, deixando log de tudo.

## Fluxo

O fluxo completo em BPMN está em [`docs/fluxo_bot.bpmn`](docs/fluxo_bot.bpmn) (abre em <https://demo.bpmn.io>).

```
A cada hora
 └─ Buscar relatos (GET /api/relatos, 3 tentativas)
     ├─ falhou ──► registra no log ──► FIM com código 1
     └─ ok ──► Validar cada relato ──► inválidos vão para a quarentena
                └─ Unir duplicados (mesmo tipo a até 25 m)
                    └─ Consultar chuva prevista por região (Open-Meteo, próximas 3 h)
                        ├─ falhou ──► usa a última previsão salva (marca "previsão antiga")
                        └─ Para cada perigo, decidir:
                              alta  + chuva ≥ 1 mm ──► alerta CRÍTICO
                              média + chuva ≥ 1 mm ──► alerta de ATENÇÃO
                              demais casos         ──► sem alerta
                            └─ Gravar alertas.json, perigos_consolidados.csv (SP156), quarentena.json
                                └─ Publicar alertas (POST /api/alertas)
                                    ├─ ok ──► FIM com código 0
                                    └─ falhou ──► alertas ficam no arquivo ──► FIM com código 2
```

## Regras de negócio

| Regra | Onde | Valor |
| --- | --- | --- |
| Chuva relevante | `config.yaml` → `limiar_chuva_mm` | ≥ 1,0 mm em alguma das próximas 3 h |
| Nível do alerta | `src/regras.py` → `decidir()` | alta → crítico · média → atenção · baixa → nenhum |
| Duplicado | `src/regras.py` → `deduplicar()` | mesmo tipo a até 25 m; fica o mais grave |
| Validação | `src/regras.py` → `validar()` | coordenada presente e dentro de São Paulo, tipo e severidade da lista permitida |
| Idempotência | `src/bot.py` → `id_alerta()` | mesmo perigo + nível + janela de 3 h = mesmo id; reexecutar não duplica |

As mesmas regras estão no FAQ da base de conhecimento do assistente (repositório `ia`), para que o bot e o assistente nunca se contradigam.

## Exceções tratadas

| Falha | O que o bot faz |
| --- | --- |
| API do MVP fora do ar na leitura | 3 tentativas com espera de 2 s e 4 s; registra `FALHA` no log e termina com código 1 |
| Open-Meteo fora do ar | 3 tentativas; usa a última previsão salva e marca o alerta com `previsao_antiga: true` |
| Sem previsão nenhuma para a região | registra o erro, não decide sobre aqueles perigos e termina como `parcial` |
| Relato sem coordenada, fora de SP, tipo ou severidade inválidos | vai para `saida/quarentena_<data>.json` com o motivo |
| Relatos duplicados | unidos em um único perigo (`qtd_relatos`, `ids_unidos`) |
| API do MVP fora do ar na publicação | alertas continuam salvos em `saida/alertas_<data>.json`; termina com código 2 |

## Integração com o MVP

- **Entrada:** `GET /api/relatos` da API do CicloAlerta.
- **Saída por API:** `POST /api/alertas`; o mapa do site lê `GET /api/alertas` e mostra a faixa de aviso e os trechos críticos.
- **Saída por arquivo:** `saida/alertas_<data>.json` e `saida/perigos_consolidados_<data>.csv` (pronto para abrir pedidos no SP156, com link do Google Maps de cada ponto).
- **Outro consumidor:** o agente do assistente (repositório `ia`) consulta os alertas criados por este bot para responder "tem alerta crítico agora?".

Enquanto a URL pública do grupo não está no ar, a pasta [`mock_mvp/`](mock_mvp) implementa o mesmo contrato e um mapa simples.

## Como rodar

Requisitos: Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 1. Subir o MVP local (mapa em http://127.0.0.1:8000)
python mock_mvp/gerar_relatos.py
uvicorn mock_mvp.app:app --port 8000

# 2. Em outro terminal, rodar o bot
python -m src.bot                       # uma execução, com a previsão real
python -m src.bot --simular-chuva 5     # demonstração em dia seco (fica marcado no log e nos alertas)
python -m src.bot --a-cada 60           # modo agendado, de hora em hora

# Apontar para a API pública do grupo
set MVP_URL=https://<url-do-mvp>        # Linux/macOS: export MVP_URL=...

# 3. Testes
pytest -v
```

Agendamento em produção: Agendador de Tarefas do Windows ou `cron` (`0 * * * * cd /app/rpa && python -m src.bot`).

## Logs e auditoria

- `logs/bot_<data>.log`: linha a linha, com data e hora, cada relato em quarentena, cada duplicado unido, cada tentativa que falhou e o resumo final.
- `logs/execucoes.jsonl`: uma linha por execução com lidos, válidos, quarentena, duplicados, alertas por nível, status e duração.
- Os logs **nunca** registram dados pessoais: só ids de relatos e contagens.

## Testes

| Cenário | Teste |
| --- | --- |
| Sucesso | `tests/test_bot.py::test_sucesso_com_chuva`: 5 relatos → 1 quarentena, 1 duplicado, 1 crítico, 1 atenção |
| Decisão | `tests/test_regras.py::test_decisao_alerta` e `test_bot.py::test_decisao_mesmo_relato_sem_chuva_nao_gera_alerta` |
| Falha | `tests/test_bot.py::test_falha_api_do_mvp_fora_do_ar`, `test_open_meteo_fora_usa_previsao_salva`, `test_publicacao_falha_vira_sucesso_parcial` |

## Segurança e LGPD

- Nenhuma credencial: o Open-Meteo não exige chave, e a URL do MVP vem de `config.yaml` ou da variável `MVP_URL`.
- O bot só lê localização do buraco, tipo e severidade. Se a API mandar um identificador de quem reportou (`autor_hash`), ele não é copiado para alertas, CSV ou logs.
- Os relatos de `mock_mvp/relatos_seed.json` são **simulados** (geração explicada em `mock_mvp/gerar_relatos.py`, semente fixa).

## Estrutura

```
src/        código do bot (bot.py, regras.py, clientes.py)
tests/      testes de sucesso, decisão e falha (pytest)
docs/       fluxo em BPMN
mock_mvp/   MVP local com o mesmo contrato de API e mapa
logs/       amostras de logs gerados (sem dados sensíveis)
saida/      amostras das saídas (alertas, CSV para o SP156, quarentena)
assets/     prints e evidências
config.yaml regras e parâmetros
```
