/**
 * Bun dev server — serves frontend static files,
 * watches src/ for changes and rebuilds automatically.
 *
 * Proxies /mission/* and /config to the backend (localhost:8000).
 * WebSocket connects directly to backend from the browser.
 *
 * Usage:  bun run dev.ts
 */

import { watch } from "fs";

const BACKEND = "http://localhost:8000";

function dlog(scope: string, message: string, payload?: unknown): void {
  const prefix = `[dev] ${new Date().toISOString()} [${scope}] ${message}`;
  if (payload === undefined) {
    console.log(prefix);
    return;
  }
  console.log(prefix, payload);
}

async function build() {
  dlog("build", "Build started");
  const result = await Bun.build({
    entrypoints: ["./src/main.tsx"],
    outdir: "./dist",
    target: "browser",
    sourcemap: "linked",
  });
  if (!result.success) {
    console.error("[build] FAILED", { logs: result.logs.length });
    for (const msg of result.logs) console.error(msg);
  } else {
    dlog("build", "Build completed", { outputs: result.outputs.length });
  }
}

await build();

const server = Bun.serve({
  port: 3000,
  async fetch(req) {
    const url = new URL(req.url);
    dlog("fetch", "Incoming request", {
      method: req.method,
      path: url.pathname,
    });

    // Proxy API requests to backend
    if (
      url.pathname.startsWith("/mission") ||
      url.pathname.startsWith("/config")
    ) {
      try {
        dlog("proxy", "Forwarding request to backend", {
          path: url.pathname,
          query: url.search,
        });
        return await fetch(`${BACKEND}${url.pathname}${url.search}`, {
          method: req.method,
          headers: req.headers,
          body: req.body,
        });
      } catch {
        dlog("proxy", "Backend unavailable", { path: url.pathname });
        return new Response("Backend unavailable", { status: 502 });
      }
    }

    // Serve static files
    let path = url.pathname === "/" ? "/index.html" : url.pathname;
    const file = Bun.file("." + path);
    if (await file.exists()) {
      dlog("static", "Serving static file", { path });
      return new Response(file);
    }

    // SPA fallback
    dlog("static", "Serving SPA fallback", { path });
    return new Response(Bun.file("./index.html"));
  },
});

dlog("server", `http://localhost:${server.port} (backend proxy → ${BACKEND})`);

// Watch source and rebuild on change
watch("./src", { recursive: true }, async (_event, filename) => {
  dlog("watch", "Source changed", { filename });
  await build();
});
