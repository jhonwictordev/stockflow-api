# Política de Segurança

## Versões suportadas

O branch principal é a versão mantida deste projeto de portfólio. Correções de
segurança devem ser aplicadas sobre ele e publicadas em uma nova versão.

## Como relatar uma vulnerabilidade

Não abra uma issue pública contendo credenciais, dados pessoais ou instruções
detalhadas de exploração. Use o canal privado de security advisory do GitHub do
repositório em que o projeto for publicado.

Inclua, quando possível:

- componente e versão afetados;
- impacto observado;
- passos mínimos para reprodução;
- sugestão de correção ou mitigação.

## Premissas de implantação

- Gere uma `SECRET_KEY` aleatória e armazene-a em um secret manager.
- Gere uma senha exclusiva para o PostgreSQL; nunca use valores de exemplo.
- Restrinja `CORS_ORIGINS` aos frontends autorizados.
- Configure `ALLOWED_HOSTS` com os domínios públicos da API.
- Use PostgreSQL, TLS e um reverse proxy ou API gateway em produção.
- Mantenha o rate limiting distribuído no gateway; o limitador interno é por processo.
- Execute migrações em uma etapa única do deploy, antes de escalar réplicas.
- Não execute `app.cli.seed_demo` em produção.
- Atualize dependências e imagens de container regularmente.
- Mantenha Secret Scanning, Dependabot, CodeQL e proteção da branch habilitados.

Tokens JWT deixam de funcionar quando expiram ou quando o usuário é desativado.
A aplicação consulta o usuário no banco em toda requisição autenticada, portanto
mudanças de função e desativação têm efeito imediato.
