# StockFlow API

API RESTful de gestão de estoque e vendas para um SaaS multi-tenant simples. O
projeto demonstra FastAPI assíncrono, arquitetura em camadas, isolamento por
organização, RBAC, JWT, transações de estoque, migrações e testes de integração.

## Demonstração e evidências

[Abrir demonstração pública](https://jhonwictordev.github.io/stockflow-api/) ·
[Assistir ao vídeo narrado de 1 minuto](https://jhonwictordev.github.io/stockflow-api/stockflow-demo.mp4) ·
[Reproduzir os testes](docs/POSTGRES_TESTING.md)

A página apresenta uma **execução gravada com dados fictícios**, vídeo em motion
design narrado e legendado em português, além de traces consultáveis. Não é uma
API hospedada: o vídeo visualiza dados de um
teste real de FastAPI + PostgreSQL, e a página não simula o backend em JavaScript.
Para experimentar a API e o painel interativo, use a execução local/Compose abaixo.

Na [execução de referência](https://github.com/jhonwictordev/stockflow-api/actions/runs/33846711745),
os **40 testes no PostgreSQL 16.15 passaram, sem skips**. A última unidade foi
disputada em cinco cenários isolados. Antes de soltar a linha, cada teste confirmou
dois PIDs realmente bloqueados por `FOR UPDATE`; depois, exigiu:

| Resultado | Estado confirmado no banco |
|---|---|
| Uma resposta `201`, outra `422` | Uma única venda e um único item |
| Saldo final `0` | Uma única movimentação de saída |
| Um commit e um rollback | Nenhuma alteração parcial da tentativa rejeitada |

### Exemplo real de trace

![Trace OpenTelemetry de uma venda concorrente no PostgreSQL](docs/examples/trace-example.svg)

Exemplo capturado em 04/09/2026, commit `86217d7`, com `request_id=demo-purchase-b`.
A compra B confirmou o commit; a compra A fez rollback por falta de estoque. O
vencedor não é fixo nem presumido pelo teste. Os tempos incluem uma barreira
deliberada e **não representam um benchmark**. O [JSON versionado](docs/examples/last-item-race.json)
contém os dois traces e a origem verificável da execução.

No Tempo, uma requisição pode ser encontrada com:

```traceql
{ resource.service.name = "stockflow-api" && span.request.id = "<X-Request-ID>" }
```

O exemplo versionado é um export do teste; ele não é automaticamente importado
no seu Tempo local. Na demonstração pública, o CI gera uma evidência nova para
cada publicação aprovada da `main`.

## Principais recursos

- Cadastro de organização com criação automática do usuário `owner`.
- Login OAuth2 Password Flow e access token JWT com expiração.
- Cinco funções: `owner`, `admin`, `manager`, `salesperson` e `viewer`.
- Isolamento de usuários, produtos, vendas e movimentações por `tenant_id`.
- Catálogo de produtos, busca, paginação e filtro de estoque baixo.
- Ajustes de estoque com trilha de movimentações.
- Venda atômica com snapshot de preço/produto e baixa de estoque.
- Cancelamento protegido contra reposição duplicada, com auditoria.
- SQLite na suíte rápida e PostgreSQL na integração, Docker e produção.
- OpenAPI/Swagger e ReDoc gerados automaticamente.
- Página inicial responsiva, em português, para apresentação do projeto.
- Painel administrativo completo para demonstrar autenticação, produtos, estoque,
  vendas e usuários diretamente no navegador.
- Comando idempotente para carregar uma organização e produtos demonstrativos.
- Tracing OpenTelemetry de requisições e transações, correlacionado por
  `request_id`, com métricas de negócio sem identificação do tenant.
- Stack local com Collector, Prometheus, Tempo, Grafana e dashboard versionado.

## Arquitetura

```text
app/
├── api/
│   ├── dependencies.py       # autenticação e autorização centralizadas
│   └── v1/
│       ├── endpoints/        # auth, users, products e sales
│       └── router.py
├── core/                     # settings, banco, segurança e exceções
├── models/                   # entidades e constraints SQLAlchemy
├── schemas/                  # contratos Pydantic V2
├── services/                 # casos de uso e regras de negócio
├── static/                   # painel administrativo responsivo
├── cli/                      # utilitários, incluindo carga demo
├── tests/                    # testes unitários e de integração
└── main.py                   # composição da aplicação
alembic/                      # migrações versionadas
observability/                # Collector, Prometheus, Tempo e Grafana
demo/                         # apresentação pública das evidências e do vídeo
scripts/build_demo.py         # vídeo e trace visual gerados a partir do CI real
```

O endpoint recebe e valida o contrato, a dependência resolve identidade e
permissão, e o serviço executa a regra de negócio. Os serviços nunca confiam em
um `tenant_id` vindo do cliente: o escopo é obtido do usuário autenticado.

```mermaid
flowchart LR
    Client --> API[FastAPI endpoint]
    API --> Auth[JWT + RBAC dependency]
    API --> Service[Business service]
    Service --> ORM[SQLAlchemy async]
    ORM --> DB[(SQLite / PostgreSQL)]
```

## Matriz de permissões

| Ação | Owner | Admin | Manager | Salesperson | Viewer |
|---|:---:|:---:|:---:|:---:|:---:|
| Consultar produtos e vendas | ✓ | ✓ | ✓ | ✓ | ✓ |
| Criar/editar produto e ajustar estoque | ✓ | ✓ | ✓ | — | — |
| Desativar produto | ✓ | ✓ | — | — | — |
| Criar venda | ✓ | ✓ | ✓ | ✓ | — |
| Cancelar venda | ✓ | ✓ | ✓ | — | — |
| Gerenciar usuários | ✓ | ✓* | — | — | — |

\* Um usuário só pode atribuir funções abaixo da sua própria hierarquia; o
`owner` não pode ser alterado ou criado pela API de usuários.

## Execução local com SQLite

Requer Python 3.11 ou superior.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env       # Windows: copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Acesse:

- Apresentação: <http://localhost:8000/>
- Painel administrativo: <http://localhost:8000/painel>
- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Health check: <http://localhost:8000/health>

## Execução com Docker e PostgreSQL

Defina segredos distintos para a API e o PostgreSQL antes de subir os serviços:

```bash
export SECRET_KEY="$(openssl rand -hex 32)"
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export GRAFANA_ADMIN_PASSWORD="$(openssl rand -hex 24)"
docker compose up --build
```

No PowerShell:

```powershell
$env:SECRET_KEY = '<segredo-aleatorio-com-32-ou-mais-caracteres>'
$env:POSTGRES_PASSWORD = '<senha-exclusiva-do-banco>'
$env:GRAFANA_ADMIN_PASSWORD = '<senha-exclusiva-do-grafana>'
docker compose up --build
```

O container da API aplica `alembic upgrade head` antes de iniciar.
No Compose, a documentação interativa permanece desativada por padrão; defina
`ENABLE_DOCS=true` apenas no ambiente local se quiser expor Swagger e ReDoc.

A stack também disponibiliza, somente no host local:

- Grafana e dashboard StockFlow: <http://localhost:3001>
- Prometheus: <http://localhost:9090>
- Tempo: <http://localhost:3200>
- Receiver OTLP/HTTP do Collector: <http://localhost:4318>

Para produção, configure também `ENVIRONMENT=production`, `ALLOWED_HOSTS` com
o domínio público e `CORS_ORIGINS` somente com origens HTTPS autorizadas. Swagger,
ReDoc e OpenAPI ficam desativados por padrão nesse ambiente. Publique a API atrás
de um reverse proxy com TLS e rate limiting distribuído; o limitador interno é uma
segunda camada por processo.

## Observabilidade de vendas

O fluxo `POST /api/v1/sales` produz um trace com os spans de servidor HTTP,
autenticação JWT, consulta do usuário, decisão RBAC, transação, consulta de
produtos, bloqueio pessimista, persistência, commit ou rollback e consulta do
resultado. O header `X-Request-ID` devolvido pela API também é gravado em cada
span como `request.id`, permitindo encontrar a execução no Tempo sem transformar
esse identificador em label de métrica.

Métricas exportadas pelo aplicativo:

- `stockflow.sales.completed`: commits de vendas confirmados;
- `stockflow.sales.rollbacks`: transações de venda revertidas;
- `stockflow.sales.insufficient_stock`: rejeições por falta de estoque;
- `stockflow.sales.transaction.duration`: histograma de duração da transação.

As métricas não recebem e-mail, nome, usuário, produto, `tenant_id` nem
`request_id`. O Collector remove esses atributos defensivamente caso sejam
adicionados por engano no futuro. Consulte [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md)
para operação, consultas PromQL/TraceQL e decisões de privacidade.

## Fluxo rápido da API

Cadastre a primeira organização:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "organization_name": "Acme",
    "full_name": "Ana Admin",
    "email": "ana@acme.test",
    "password": "uma-senha-segura"
  }'
```

Use o `access_token` retornado como `Authorization: Bearer <token>`. O login
posterior usa `application/x-www-form-urlencoded`, com o e-mail no campo
`username`, conforme o fluxo OAuth2 usado pelo Swagger.

### Dados de demonstração

Em um ambiente local, carregue uma organização e três produtos de exemplo:

```bash
python -m app.cli.seed_demo
```

Credenciais padrão da carga local:

- E-mail: `demo@stockflow.dev`
- Senha: `Demo@StockFlow123`

O comando é idempotente e recusa execução quando `ENVIRONMENT=production`.
E-mail e senha podem ser alterados com `--email` e `--password`.

## Controles de segurança

- `SECRET_KEY` obrigatória e validação fail-fast de configurações de produção;
- JWT HS256 com issuer, audience, tipo, emissão e expiração obrigatórios;
- bcrypt, senha mínima de 12 caracteres e proteção contra enumeração por timing;
- rate limit nos endpoints de autenticação e limite global de payload;
- CORS explícito, hosts confiáveis, CSP, HSTS em produção e demais headers;
- contêiner Alpine não-root, somente leitura, sem capabilities e sem privilégios;
- Bandit, `pip-audit`, CodeQL, Dependabot e ações fixadas por commit no CI;
- isolamento por `tenant_id` e autorização RBAC validada no banco a cada requisição.
- telemetria sem PII/tenant nas métricas e correlação de traces por ID opaco.

Endpoints principais:

- `POST /api/v1/auth/register` e `POST /api/v1/auth/token`
- `GET /api/v1/auth/me`
- `GET /api/v1/dashboard/summary`
- `POST|GET|PATCH /api/v1/users`
- `POST|GET|PATCH|DELETE /api/v1/products`
- `POST /api/v1/products/{id}/stock-adjustments`
- `GET /api/v1/products/{id}/stock-movements`
- `POST|GET /api/v1/sales`
- `POST /api/v1/sales/{id}/cancel`

## Decisões de segurança e consistência

| Decisão | Justificativa e limite |
|---|---|
| Uma `AsyncSession` por requisição | Sessões são estado mutável de uma transação; não podem ser compartilhadas entre tarefas concorrentes. |
| `SELECT FOR UPDATE` no PostgreSQL | Protege o saldo entre processos/réplicas, ao contrário de um lock apenas em memória Python. Após esperar, a próxima compra lê o saldo confirmado. |
| Locks ordenados por UUID | Reduz deadlocks ao vender vários produtos em ordens diferentes; não garante ausência de deadlocks em qualquer operação futura. |
| `READ COMMITTED` + transação atômica | Adequado à invariante por linha neste fluxo. Venda, itens, saldo e movimentação confirmam ou revertem juntos. |
| PostgreSQL real além de SQLite | SQLite não exerce `FOR UPDATE`; os testes de integração usam conexões distintas e schemas criados por Alembic, sem uma transação compartilhada que mascare commits. |
| Spans manuais e métricas agregadas | Mostram regras de negócio sem exportar SQL com parâmetros, JWT ou dados pessoais. `request_id` fica nos spans/logs, não em labels. |
| Camadas modulares, sem abstrações redundantes | Endpoints tratam HTTP, serviços concentram regras e SQLAlchemy cuida da persistência. Não se afirma um domínio independente do ORM: esse acoplamento foi aceito para manter o projeto pequeno e legível. |

As bases dessas escolhas estão nas documentações de
[locks do PostgreSQL](https://www.postgresql.org/docs/16/explicit-locking.html) e
[concorrência de sessões SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks).

- Senhas nunca são armazenadas em texto puro; `bcrypt` aplica salt e custo.
- O token contém identidade e contexto, mas o usuário e seu estado ativo são
  novamente validados no banco em cada requisição.
- E-mails são globalmente únicos para permitir login não ambíguo sem pedir o
  tenant no OAuth2 Password Flow.
- Operações de estoque usam transação e `SELECT ... FOR UPDATE` (efetivo no
  PostgreSQL) para impedir venda concorrente acima do saldo.
- Valores monetários usam `Decimal`/`NUMERIC`, nunca ponto flutuante.
- Exclusão de produto é lógica, preservando o histórico de vendas.
- Itens de venda guardam nome, SKU e preço como snapshot histórico.

Para produção, mantenha `SECRET_KEY` em um secret manager, restrinja CORS,
execute atrás de TLS/reverse proxy e aplique rate limiting no gateway.

## Testes e qualidade

```bash
pytest
pytest --database=postgres --evidence-dir=outputs/evidence
ruff check .
ruff format --check .
mypy app
alembic check
```

A suíte padrão usa SQLite em memória. A execução PostgreSQL requer
`TEST_POSTGRES_URL` apontando para um banco descartável terminado em `_test`;
consulte o [comando completo e as proteções da fixture](docs/POSTGRES_TESTING.md).
Os mesmos testes funcionais rodam nos dois bancos; os oito casos concorrentes
são exclusivos de PostgreSQL e aparecem como skips explícitos no SQLite.

O CI executa qualidade/segurança, integração PostgreSQL, build de imagens,
observabilidade ponta a ponta e geração da demonstração. As evidências e o vídeo
ficam nos artefatos `postgres-evidence` e `stockflow-demo`. O GitHub Pages só é
atualizado pela `main` após os jobs aprovados, sem publicar segredos ou bancos.

Atalhos equivalentes estão disponíveis no `Makefile`, por exemplo `make quality`,
`make seed` e `make docker-up`.

Consulte `CONTRIBUTING.md` para o fluxo de colaboração e `SECURITY.md` para as
premissas de implantação e comunicação responsável de vulnerabilidades.
Uma descrição mais profunda das decisões técnicas está em `docs/ARCHITECTURE.md`.

Limites conhecidos: esta versão não implementa chave de idempotência para criação
de vendas, retries automáticos de deadlock, refresh token ou rate limit
distribuído. A disputa de duas compras diferentes não comprova proteção contra
reenvio da mesma compra após um timeout de rede.

## Migrações futuras

Após alterar modelos:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Revise sempre a migração gerada antes de aplicá-la em produção.
