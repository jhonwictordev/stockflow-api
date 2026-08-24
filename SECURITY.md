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
- Restrinja `CORS_ORIGINS` aos frontends autorizados.
- Use PostgreSQL, TLS e um reverse proxy ou API gateway em produção.
- Aplique rate limiting no gateway e monitore falhas de autenticação.
- Execute migrações em uma etapa única do deploy, antes de escalar réplicas.
- Não execute `app.cli.seed_demo` em produção.
- Atualize dependências e imagens de container regularmente.

Tokens JWT deixam de funcionar quando expiram ou quando o usuário é desativado.
A aplicação consulta o usuário no banco em toda requisição autenticada, portanto
mudanças de função e desativação têm efeito imediato.
