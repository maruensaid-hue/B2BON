const API_ORIGIN = "https://b2bon-api-staging.onrender.com";

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);

    // Keep the API path/query intact; the browser talks to this same-origin
    // Worker, which forwards the request to the isolated staging API.
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
