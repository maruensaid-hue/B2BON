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
      return fetch(upstreamRequest);
    }

    return env.ASSETS.fetch(request);
  },
};
