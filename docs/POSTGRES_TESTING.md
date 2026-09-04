# Integração e concorrência no PostgreSQL

## Dois bancos, responsabilidades diferentes

`pytest` mantém a suíte rápida no SQLite em memória. `pytest --database=postgres`
executa os mesmos contratos de autenticação, RBAC, isolamento de tenants, produtos,
vendas e observabilidade no PostgreSQL e habilita os testes específicos de locks.
Não há fallback para SQLite quando PostgreSQL foi solicitado: erro de conexão ou
configuração falha a execução.

O SQLite não implementa `SELECT FOR UPDATE`. Portanto, um teste de saldo final
rodando apenas em SQLite não comprova a proteção contra overselling em produção.

## Executar localmente

Use exclusivamente um banco descartável cujo nome termine em `_test`. A fixture
nunca reutiliza `DATABASE_URL`, não trunca tabelas compartilhadas e cria um schema
aleatório por caso. Apenas esse schema é removido no teardown, inclusive em falhas.

```bash
docker compose -p stockflow-tests -f docker-compose.test.yml up -d --wait
export TEST_POSTGRES_URL='postgresql+asyncpg://stockflow:local-test-only@localhost:55432/stockflow_test'
pytest --database=postgres --evidence-dir=outputs/evidence
docker compose -p stockflow-tests -f docker-compose.test.yml down
```

No PowerShell, substitua a linha `export` por:

```powershell
$env:TEST_POSTGRES_URL = 'postgresql+asyncpg://stockflow:local-test-only@localhost:55432/stockflow_test'
```

A senha acima pertence somente ao banco descartável de teste, vinculado a
`127.0.0.1:55432`; nunca a utilize em uma implantação. Não conecte esta suíte a um
banco de produção, mesmo que seu nome termine em `_test`.

Para executar apenas os cenários concorrentes:

```bash
pytest --database=postgres -m postgres -v
```

## Como a disputa é comprovada

1. As migrações Alembic criam o schema real de cada teste; não se usa `create_all`
   no PostgreSQL. O teste verifica também `alembic_version` e `READ COMMITTED`.
2. Uma conexão de controle segura a linha do produto com `FOR UPDATE`.
3. Duas tarefas HTTPX enviam `POST /api/v1/sales` à aplicação ASGI. Cada requisição
   recebe sua própria `AsyncSession` e conexão; a fixture não compartilha uma
   transação externa com as requisições.
4. Outra conexão consulta `pg_stat_activity` e `pg_blocking_pids()`. O teste só
   avança após confirmar dois PIDs distintos com `wait_event_type = 'Lock'`, ambos
   executando `FOR UPDATE`. Remover o lock da consulta impede essa confirmação.
5. O teste libera a linha e espera as respostas com timeout. Exige `[201, 422]`,
   saldo zero, uma venda, um item e uma única movimentação de saída. As métricas
   registram um commit, um rollback e uma rejeição por falta de estoque.
6. Os spans devem conter exatamente um commit e um rollback. O cenário é repetido
   cinco vezes, com schema e conexões novos em cada repetição.

Não se usa `sleep` fixo para presumir que houve uma disputa. A espera curta entre
consultas apenas evita polling intenso; é o estado observado no banco que libera
a barreira. Timeouts limitam falhas e o teardown cancela tarefas remanescentes.

## Cobertura adicional

| Cenário | Invariante verificada |
|---|---|
| Última unidade, cinco repetições | Uma venda; saldo zero; nenhum registro parcial |
| Dois produtos em ordens inversas | Duas vendas sem deadlock no cenário; saldos corretos |
| Dois cancelamentos da mesma venda | Uma restauração de estoque; segunda resposta 409 |
| Venda inválida seguida por compra aguardando | Rollback libera locks; compra válida confirma |
| Suíte funcional completa | Mesmos contratos e isolamento no SQLite e PostgreSQL |

Ordenar a aquisição dos locks reduz deadlocks nesse fluxo, mas não é uma garantia
universal para novas operações. Não há retries automáticos nem chave de
idempotência de vendas nesta versão. Duas compras legítimas distintas não são o
mesmo problema de um cliente repetir a mesma requisição após timeout.

O transporte HTTPX/ASGI cobre rotas, dependências, validação e serviços reais,
mas não testa sockets TCP da API. O job `observability` complementa a suíte com
HTTP real via Uvicorn, PostgreSQL e a stack do Compose.

## Evidências e vídeo

`--evidence-dir` é opcional e só exporta o cenário sintético da última unidade
após todas as suas asserções. Há uma allowlist de atributos de spans; não são
exportados token, corpo da requisição, SQL com parâmetros, UUID de tenant, cliente,
produto ou usuário. O JSON contém commit, execução do CI, versão do banco e tempos
reais. Os tempos incluem a barreira deliberada: **não são benchmark**.

```bash
pip install -r requirements-demo.txt
python scripts/build_demo.py --evidence outputs/evidence/last-item-race.json
```

O gerador produz `outputs/site/`: página estática, JSON, SVG do trace, MP4 de 40
segundos, poster e legendas WebVTT. O vídeo é uma visualização animada dos dados
capturados, não uma gravação de tela nem uma simulação de backend em JavaScript.
No CI, o artefato `postgres-evidence` guarda evidência e JUnit; `stockflow-demo`
guarda o vídeo e a página. A publicação pelo GitHub Pages só ocorre na `main`
depois de todos os jobs de qualidade, PostgreSQL, contêineres e observabilidade.

## Referências técnicas

- [PostgreSQL 16: locks explícitos](https://www.postgresql.org/docs/16/explicit-locking.html)
- [PostgreSQL 16: pg_locks e pg_blocking_pids](https://www.postgresql.org/docs/16/view-pg-locks.html)
- [SQLAlchemy: uma AsyncSession por tarefa](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#is-the-session-thread-safe-is-asyncsession-safe-to-share-in-concurrent-tasks)
- [GitHub Pages com Actions](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
