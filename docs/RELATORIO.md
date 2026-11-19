# CicloAlerta · Relatório Técnico de Automação (RPA)

**Global Solution 2026.2 · CitizenTech · Engenharia de Software 4º ano**

**Disciplina:** Robotic Process Automation · **Atividade:** Do Processo Manual à Automação Inteligente

## 1. Integrantes

| Nome completo | RM |
| --- | --- |
| Breno Silva | RM97864 |
| Enrico Marquez | RM99325 |
| Gustavo Dias | RM550820 |
| Joel Barros | RM550378 |
| Leonardo Moreira | RM550988 |

**Repositório GitHub:** https://github.com/Leonardo-Valerio/cicloalerta-rpa

**Vídeo de demonstração (até 3 min):** https://youtu.be/HWE1H6vYt8c

## 2. A CitizenTech e o problema resolvido

O **CicloAlerta** é um site para celular que mostra, num mapa das ciclovias de São Paulo, onde há buracos e trechos
perigosos, e avisa quando a chuva deixa esses trechos mais arriscados. O cidadão atendido é o ciclista e o entregador
de bicicleta elétrica, que usa a ciclovia todos os dias e cai quando um buraco fica escondido por uma poça.

Os relatos de perigo chegam de três origens: o próprio ciclista pelo site, o detector de visão computacional e o robô
inspetor. Sem automação, alguém da operação teria de, toda hora: abrir a lista de relatos, descartar os quebrados,
juntar os repetidos, consultar a previsão do tempo de cada região, decidir quais trechos ficam perigosos, publicar o
aviso no mapa e montar a lista de pedidos de conserto. Em dia de chuva, que é justamente quando o aviso importa, esse
trabalho manual atrasa e falha.

## 3. Objetivo da automação e benefício para o cidadão

**Objetivo:** um bot que, de hora em hora e sem intervenção humana, transforma os relatos brutos em alertas
confiáveis de chuva no mapa do CicloAlerta e em uma lista consolidada de perigos pronta para o pedido de conserto no SP156.

**Benefício:**

- o ciclista recebe o aviso **antes** da chuva chegar (previsão das próximas 3 horas), não depois da queda;
- o mapa não fica poluído com relatos repetidos ou inválidos;
- a lista diária de perigos consolidados, com link de mapa de cada ponto, encurta o caminho até o conserto (SP156).

## 4. Descrição do processo e desenho do fluxo

O fluxo completo está em BPMN no repositório (`docs/fluxo_bot.bpmn`).

{{IMG_BPMN}}

| # | Etapa | Entrada | Saída |
| --- | --- | --- | --- |
| 1 | Início agendado (a cada hora) | relógio / agendador | execução iniciada |
| 2 | Buscar relatos | `GET /api/relatos` do MVP | lista de relatos |
| 3 | Validar cada relato (repetição) | lista de relatos | válidos + quarentena com motivo |
| 4 | Unir duplicados | relatos válidos | perigos únicos (`qtd_relatos`, `ids_unidos`) |
| 5 | Consultar chuva por região (repetição) | células de ~1 km | maior chuva prevista nas próximas 3 h |
| 6 | Decidir o nível de cada perigo (repetição + decisão) | severidade e chuva | crítico / atenção / sem alerta |
| 7 | Gravar saídas | alertas e perigos | `alertas_<data>.json`, `perigos_consolidados_<data>.csv`, `quarentena_<data>.json` |
| 8 | Publicar no MVP | alertas | `POST /api/alertas` |
| 9 | Fim | — | código 0 (sucesso), 2 (parcial) ou 1 (falha) + registro em `execucoes.jsonl` |

## 5. Tecnologias utilizadas e justificativa

| Tecnologia | Uso | Por que |
| --- | --- | --- |
| Python 3.11 | linguagem do bot | é a linguagem de todo o MVP (API, IA, visão); o bot fica versionado no Git e testável com pytest, o que é mais difícil em ferramentas visuais |
| `requests` | chamadas HTTP | simples e com controle de timeout |
| Open-Meteo Forecast API | previsão de chuva por hora | gratuita, sem chave (nenhum segredo a proteger), com previsão horária |
| FastAPI (MVP local) | contrato `/api/relatos` e `/api/alertas` + mapa | mesmo framework da API do produto; permite demonstrar a integração sem depender da URL pública |
| PyYAML | parâmetros em `config.yaml` | regras de negócio alteráveis sem mexer no código |
| pytest | testes automatizados | cenários de sucesso, decisão e falha reproduzíveis |
| Agendador de Tarefas / cron, ou `--a-cada 60` | execução de hora em hora | sem dependência de licença de ferramenta RPA |
| bpmn.io | desenho do fluxo | padrão BPMN 2.0, gratuito |

## 6. Regras de negócio, decisões e processamento

**Validação (decisão por item, repetição sobre a coleção).** Um relato vai para a quarentena se:
não tem coordenada; está fora da cidade de São Paulo; o tipo não é `buraco`, `desnivel`, `poca` ou `obstaculo`;
a severidade não é `baixa`, `media` ou `alta`.

**Duplicados.** Relatos do mesmo tipo a até **25 m** (distância de haversine) viram um único perigo; fica o de maior
severidade, e o perigo guarda quantos relatos o confirmam (`qtd_relatos`), o que vira um sinal de confiança.

**Decisão do alerta.**

| Severidade | Chuva prevista (máx. nas próximas 3 h) | Resultado |
| --- | --- | --- |
| alta | ≥ 1,0 mm | alerta **crítico** |
| média | ≥ 1,0 mm | alerta de **atenção** |
| baixa | qualquer | sem alerta |
| qualquer | < 1,0 mm | sem alerta |

O limiar de 1,0 mm e a janela de 3 h ficam em `config.yaml`. As mesmas regras estão no FAQ do assistente de IA do
CicloAlerta, para que o bot e o assistente nunca deem informações diferentes ao cidadão.

**Idempotência.** O id do alerta é um hash de perigo + nível + janela de 3 horas: rodar o bot duas vezes na mesma
janela não duplica alertas (na execução de demonstração abaixo, o MVP respondeu `novos: 0`).

**Processamento real (18/11/2026, 20h18, chuva real do Open-Meteo: até 3,7 mm previstos às 22h):**

| Lidos | Válidos | Quarentena | Duplicados unidos | Perigos | Críticos | Atenção | Sem alerta | Duração |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 31 | 27 | 4 | 4 | 23 | 7 | 9 | 7 | 8,7 s |

## 7. Tratamento de exceções e recuperação

| Falha prevista | Tratamento | Resultado |
| --- | --- | --- |
| API do MVP fora do ar na leitura | 3 tentativas com espera crescente (2 s, 4 s) | registra `FALHA` no log e em `execucoes.jsonl`, termina com código 1; nenhum alerta errado é gerado |
| Open-Meteo fora do ar | 3 tentativas; depois usa a última previsão salva da mesma região | alerta marcado com `previsao_antiga: true` |
| Nenhuma previsão disponível para a região | registra o erro e não decide sobre aqueles perigos | execução `parcial` (código 2) |
| Relato sem coordenada, fora de SP, tipo ou severidade inválidos | quarentena com o motivo | `quarentena_<data>.json` |
| Relatos duplicados ou inconsistentes | união por tipo e distância | perigo único com contagem |
| API do MVP fora do ar na publicação | 3 tentativas; alertas permanecem no arquivo | execução `parcial` (código 2); integração por arquivo continua valendo |
| Dia sem chuva na hora da demonstração | `--simular-chuva <mm>` | alertas e log marcados como simulação (`simulado: true`) |

Nenhuma falha é silenciosa: toda exceção gera uma linha `WARNING` ou `ERROR` no log e muda o status da execução.

## 8. Logs e evidências de auditoria

Dois registros por execução, em `logs/`:

- `bot_<data>.log`: legível, com data e hora, cada relato em quarentena e o motivo, cada duplicado unido, cada tentativa que falhou e o resumo final;
- `execucoes.jsonl`: uma linha estruturada por execução (lidos, válidos, quarentena, duplicados, alertas por nível, status, erros, duração).

Trecho real do log (execução com sucesso):

```
2026-11-18 20:18:30 | INFO    | Relatos lidos: 31
2026-11-18 20:18:30 | WARNING | Quarentena: relato r028 (sem_coordenada)
2026-11-18 20:18:30 | WARNING | Quarentena: relato r029 (tipo_invalido)
2026-11-18 20:18:30 | WARNING | Quarentena: relato r030 (fora_de_sao_paulo)
2026-11-18 20:18:30 | WARNING | Quarentena: relato r031 (severidade_invalida)
2026-11-18 20:18:30 | INFO    | Duplicado unido: relato r024
2026-11-18 20:18:35 | INFO    | Decisão: 7 críticos, 9 de atenção, 7 sem alerta
2026-11-18 20:18:37 | INFO    | Alertas publicados no MVP: {'recebidos': 16, 'novos': 16, 'total': 16}
2026-11-18 20:18:37 | INFO    | Fim: status=sucesso · lidos=31 · válidos=27 · quarentena=4 · duplicados=4 · críticos=7 · atenção=9 · 8.7 s
```

Trecho real do log (API do MVP fora do ar):

```
2026-11-18 20:18:58 | WARNING | API do MVP (GET /api/relatos): tentativa 1/3 falhou (ConnectionError)
2026-11-18 20:19:02 | WARNING | API do MVP (GET /api/relatos): tentativa 2/3 falhou (ConnectionError)
2026-11-18 20:19:08 | WARNING | API do MVP (GET /api/relatos): tentativa 3/3 falhou (ConnectionError)
2026-11-18 20:19:08 | ERROR   | FALHA: API do MVP (GET /api/relatos) indisponível após 3 tentativas. Nenhum alerta foi gerado nesta execução.
2026-11-18 20:19:08 | INFO    | Fim: status=falha · lidos=0 · ... · 12.1 s
```

## 9. Integração com o MVP

O resultado do bot é consumido por outros componentes do CicloAlerta de três formas:

1. **API:** `POST /api/alertas` grava os alertas; o mapa do site lê `GET /api/alertas`, mostra a faixa vermelha
   "Chuva prevista: N trecho(s) crítico(s)" e destaca cada trecho com um anel no mapa.
2. **Arquivo estruturado:** `saida/perigos_consolidados_<data>.csv` (separador `;`, abre no Excel), com ciclovia,
   tipo, severidade, quantidade de relatos, chuva prevista, nível de alerta e link do Google Maps, para a abertura do
   pedido de conserto no SP156.
3. **Assistente de IA:** o agente do componente Inteligência consulta `GET /api/alertas` para responder perguntas
   como "tem alerta crítico agora?".

Contrato usado (combinado pela equipe para todos os componentes):

| Rota | Quem chama | Campos |
| --- | --- | --- |
| `GET /api/relatos` | bot (leitura) | `id, lat, lon, tipo, severidade, origem, data` |
| `POST /api/alertas` | bot (escrita) | `id, relato_id, nivel, tipo, severidade, ciclovia, lat, lon, chuva_mm, previsao_antiga, simulado, criado_em, valido_ate` |
| `GET /api/alertas` | site e assistente | alertas ainda válidos |

{{IMG_MAPA}}

## 10. Testes realizados

17 testes automatizados com pytest (`pytest -v`), todos passando:

| Cenário | Teste | O que comprova |
| --- | --- | --- |
| Sucesso | `test_sucesso_com_chuva` | 5 relatos → 1 em quarentena, 1 duplicado, 1 alerta crítico, 1 de atenção, publicados e gravados em arquivo |
| Decisão | `test_decisao_alerta` (6 casos) | limiar exato, abaixo do limiar, severidade baixa |
| Decisão | `test_decisao_mesmo_relato_sem_chuva_nao_gera_alerta` | o mesmo conjunto de relatos não gera alerta sem chuva |
| Decisão | `test_validacao` (5 casos) e `test_deduplicacao...` | quarentena por motivo e união de duplicados |
| Falha | `test_falha_api_do_mvp_fora_do_ar` | 3 tentativas, `FALHA` no log, status `falha`, código 1 |
| Falha | `test_open_meteo_fora_usa_previsao_salva` | recuperação com a última previsão (`previsao_antiga`) |
| Falha | `test_publicacao_falha_vira_sucesso_parcial` | alertas preservados em arquivo, código 2 |

Além dos testes automáticos, as três execuções reais descritas nas seções 6 e 8 (chuva real, demonstração com chuva
simulada e API fora do ar) estão registradas em `logs/execucoes.jsonl`.

## 11. Segurança e LGPD

- **Sem credenciais:** o Open-Meteo não exige chave, e a URL do MVP vem de `config.yaml` ou da variável de ambiente `MVP_URL`. Nada sensível no repositório.
- **Minimização:** o bot só usa a localização do perigo, o tipo e a severidade. Não há nome, e-mail, telefone ou trajeto de pessoas. Se a API enviar um identificador de quem reportou (guardado pelo MVP apenas como hash), ele não é copiado para alertas, CSV ou logs.
- **Logs sem dado pessoal:** registram apenas ids de relatos, contagens e mensagens de erro.
- **Dados simulados identificados:** os relatos de teste são gerados por `mock_mvp/gerar_relatos.py` (semente fixa, casos inválidos de propósito) e marcados com `simulado: true`.
- **Pessoa no circuito:** o bot não abre pedidos no SP156 sozinho; ele prepara a lista consolidada para que uma pessoa revise e envie.

## 12. Links

- Repositório GitHub: https://github.com/Leonardo-Valerio/cicloalerta-rpa
- Vídeo de demonstração: https://youtu.be/HWE1H6vYt8c
