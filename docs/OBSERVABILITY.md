# Observabilidade do StockFlow

## Objetivo

A instrumentação acompanha a criação de uma venda desde o servidor HTTP até o
commit no banco. OpenTelemetry envia traces e métricas por OTLP/HTTP ao
Collector. O Collector publica métricas para o Prometheus e encaminha traces ao
Tempo; o Grafana provisiona ambos e carrega o dashboard do repositório.

## Subir o ambiente

Defina três segredos diferentes e inicie a composição:

```bash
export SECRET_KEY="$(openssl rand -hex 32)"
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export GRAFANA_ADMIN_PASSWORD="$(openssl rand -hex 24)"
docker compose up --build
```

No PowerShell:

```powershell
$env:SECRET_KEY = '<segredo-jwt-aleatorio>'
$env:POSTGRES_PASSWORD = '<senha-exclusiva-do-postgres>'
$env:GRAFANA_ADMIN_PASSWORD = '<senha-exclusiva-do-grafana>'
docker compose up --build
```

Serviços vinculados somente a `127.0.0.1`:

| Serviço | Endereço | Papel |
|---|---|---|
| API | <http://localhost:8000> | Aplicação instrumentada |
| Grafana | <http://localhost:3001> | Dashboard e exploração de traces |
| Prometheus | <http://localhost:9090> | Séries temporais |
| Tempo | <http://localhost:3200> | Armazenamento e consulta de traces |
| Collector | <http://localhost:4318> | Receiver OTLP/HTTP |

## Trace de criação de venda

Uma resposta da API contém `X-Request-ID`. No Grafana, abra **Explore**, escolha
Tempo e consulte pelo atributo de span:

```traceql
{ resource.service.name = "stockflow-api" && span.request.id = "<request-id>" }
```

O trace apresenta autenticação, RBAC, consulta, `SELECT FOR UPDATE`, persistência
e commit. Em falhas transacionais, o commit é substituído por rollback. Nomes de
cliente, e-mails, UUIDs de usuário/tenant/produto e conteúdo do JWT não são
adicionados aos spans.

IDs enviados por clientes só são aceitos quando têm de 8 a 64 caracteres e usam
letras, números, ponto, sublinhado ou hífen. Outros valores são substituídos por
UUID gerado pelo servidor, evitando que PII seja usada como identificador.

## Catálogo de métricas

| Instrumento OTel | Série Prometheus | Labels permitidas |
|---|---|---|
| `stockflow.sales.completed` | `stockflow_sales_completed_total` | nenhuma |
| `stockflow.sales.rollbacks` | `stockflow_sales_rollbacks_total` | nenhuma |
| `stockflow.sales.insufficient_stock` | `stockflow_sales_insufficient_stock_total` | nenhuma |
| `stockflow.sales.transaction.duration` | `stockflow_sales_transaction_duration_seconds_*` | `outcome` |

Exemplos PromQL:

```promql
sum(rate(stockflow_sales_completed_total[5m]))
sum(increase(stockflow_sales_rollbacks_total[1h]))
histogram_quantile(
  0.95,
  sum by (le) (
    rate(stockflow_sales_transaction_duration_seconds_bucket[5m])
  )
)
```

`tenant_id`, usuário, cliente, produto e `request_id` são proibidos em métricas.
Além das assinaturas restritas no código, o processador
`transform/metrics_privacy` remove essas chaves no Collector.

## Configuração

| Variável | Padrão | Descrição |
|---|---:|---|
| `OTEL_ENABLED` | `false` | Ativa exportação; o Compose usa `true` |
| `OTEL_SERVICE_NAME` | `stockflow-api` | Recurso `service.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | Base OTLP/HTTP |
| `OTEL_EXPORT_INTERVAL_MILLISECONDS` | `5000` | Intervalo de métricas |
| `OTEL_EXPORT_TIMEOUT_SECONDS` | `10` | Timeout de exportação |
| `OTEL_TRACE_SAMPLE_RATIO` | `1.0` | Amostragem entre `0.0` e `1.0` |

Em produção, use TLS entre aplicação, Collector e backends, autenticação no
Grafana, retenção adequada, amostragem menor que 100% quando necessário e acesso
de rede privado aos receivers. A indisponibilidade do Collector não participa da
transação de negócio: exportadores trabalham em lote e não devem impedir vendas.
