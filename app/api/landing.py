from textwrap import dedent


def render_landing_page() -> str:
    """Return a dependency-free presentation page for the backend project."""

    return dedent(
        """\
        <!doctype html>
        <html lang="pt-BR">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>StockFlow API</title>
          <style>
            :root {
              color-scheme: dark;
              font-family: Inter, ui-sans-serif, system-ui, sans-serif;
              background: #07111f;
              color: #dce9f7;
            }
            * { box-sizing: border-box; }
            body {
              margin: 0;
              min-height: 100vh;
              display: grid;
              place-items: center;
              background:
                radial-gradient(circle at 15% 10%, #123660 0, transparent 35%),
                radial-gradient(circle at 90% 80%, #123f39 0, transparent 35%),
                #07111f;
            }
            main { width: min(920px, calc(100% - 32px)); padding: 52px 0; }
            .eyebrow { color: #5eead4; font-weight: 700; letter-spacing: .12em; }
            h1 { margin: 12px 0; font-size: clamp(3rem, 9vw, 6.5rem); line-height: .95; }
            .lead { max-width: 720px; color: #9db1c7; font-size: 1.2rem; line-height: 1.7; }
            .actions { display: flex; gap: 12px; flex-wrap: wrap; margin: 32px 0 44px; }
            a {
              color: #07111f;
              background: #5eead4;
              padding: 13px 18px;
              border-radius: 10px;
              text-decoration: none;
              font-weight: 750;
            }
            a.secondary { color: #dce9f7; background: #15283d; }
            .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
            article { padding: 22px; border: 1px solid #223950; border-radius: 14px; background: #0b1928cc; }
            article strong { display: block; color: #7dd3fc; margin-bottom: 8px; }
            article span { color: #8fa6bd; line-height: 1.55; }
            footer { margin-top: 34px; color: #668096; font-size: .9rem; }
            @media (max-width: 700px) { .grid { grid-template-columns: 1fr; } }
          </style>
        </head>
        <body>
          <main>
            <div class="eyebrow">FASTAPI · MULTI-TENANT · RBAC</div>
            <h1>StockFlow</h1>
            <p class="lead">
              API assíncrona para gestão de estoque e vendas, construída com
              arquitetura em camadas, autenticação JWT e consistência transacional.
            </p>
            <nav class="actions" aria-label="Documentação da API">
              <a href="/painel">Acessar painel</a>
              <a class="secondary" href="/docs">Explorar no Swagger</a>
              <a class="secondary" href="/redoc">Abrir ReDoc</a>
              <a class="secondary" href="/health">Verificar saúde</a>
            </nav>
            <section class="grid">
              <article><strong>Multi-tenant</strong><span>Isolamento de dados por organização em todas as operações.</span></article>
              <article><strong>Segurança</strong><span>OAuth2, JWT, bcrypt e cinco níveis de autorização RBAC.</span></article>
              <article><strong>Consistência</strong><span>Vendas atômicas, bloqueio de estoque e trilha de movimentações.</span></article>
            </section>
            <footer>StockFlow API · Python · FastAPI · SQLAlchemy</footer>
          </main>
        </body>
        </html>
        """
    )
