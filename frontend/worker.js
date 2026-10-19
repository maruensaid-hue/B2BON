const API_ORIGIN = "https://b2bon-api.onrender.com";

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);

    // Browser requests stay on the production Worker origin. Forward the
    // original Cookie and Origin headers to the API so HttpOnly session
    // cookies work as first-party cookies without weakening CSRF checks.
    if (incoming.pathname === "/api" || incoming.pathname.startsWith("/api/")) {
      const target = new URL(incoming.pathname + incoming.search, API_ORIGIN);
      const headers = new Headers(request.headers);
      headers.delete("host");
      headers.delete("cookie2");

      const upstreamRequest = new Request(target, {
        method: request.method,
        headers,
        body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
        redirect: "manual",
      });
      // A API gratuita do Render dorme e pode levar mais de 100 s para acordar, tempo em que o Cloudflare derruba a
      // conexão sem explicação. Antes disso devolvemos um 503 claro: a API continua acordando e a próxima tentativa
      // (a tela repete sozinha) já a encontra pronta.
      const limiteMs = Number(env.API_TIMEOUT_MS) || 85000;
      const controle = new AbortController();
      const temporizador = setTimeout(() => controle.abort(), limiteMs);
      try {
        return await fetch(upstreamRequest, { signal: controle.signal });
      } catch (erro) {
        if (controle.signal.aborted) {
          return new Response(
            JSON.stringify({ detalhe: "O servidor estava ocioso e está iniciando. Tente novamente em instantes." }),
            { status: 503, headers: { "content-type": "application/json", "retry-after": "10" } },
          );
        }
        throw erro;
      } finally {
        clearTimeout(temporizador);
      }
    }

    return env.ASSETS.fetch(request);
  },

  // Agendador do Cloudflare (UTC, ver wrangler.toml): a API gratuita do Render dorme após 15 min sem uso. Este toque a
  // cada 10 min em horário comercial evita a espera de ~2 min para acordar. Fora do horário ela dorme e economiza as
  // 750 h gratuitas do mês.
  async scheduled(_controller, _env, ctx) {
    ctx.waitUntil(fetch(`${API_ORIGIN}/health`).catch(() => undefined));
  },
};
