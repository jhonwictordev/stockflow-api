# Contribuindo com o StockFlow

Obrigado pelo interesse em contribuir. O projeto prioriza isolamento de tenant,
regras de negócio explícitas e alterações acompanhadas por testes.

## Ambiente de desenvolvimento

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
```

## Fluxo recomendado

1. Crie uma branch curta e descritiva.
2. Mantenha regras de negócio em `app/services`, não nos endpoints.
3. Toda consulta de domínio deve aplicar o `tenant_id` do usuário autenticado.
4. Adicione ou atualize testes para mudanças de comportamento.
5. Execute a verificação completa antes de abrir o pull request.

```bash
ruff check .
ruff format --check .
mypy app
pytest
alembic check
```

## Migrações

Mudanças em modelos persistentes exigem uma migração Alembic revisada:

```bash
alembic revision --autogenerate -m "descricao da alteracao"
alembic upgrade head
alembic check
```

Evite editar uma migração que já possa ter sido aplicada por outras pessoas;
crie uma nova revisão.

## Commits e pull requests

- Use mensagens no imperativo e explique o motivo da alteração.
- Mantenha o pull request focado em uma responsabilidade.
- Descreva impacto em segurança, banco e compatibilidade da API quando houver.
- Nunca inclua `.env`, bancos locais, tokens ou credenciais.
