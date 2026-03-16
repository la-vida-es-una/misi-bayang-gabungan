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

async function build() {
  const result = await Bun.build({
    entrypoints: ["./src/main.tsx"],
    outdir: "./dist",
    target: "browser",
    sourcemap: "linked",
  });
  if (!result.success) {
    console.error("[build] FAILED");
    for (const msg of result.logs) console.error(msg);
  } else {
    console.log("[build] OK");
  }
}

await build();

const server = Bun.serve({
  port: 3000,
  async fetch(req) {
    const url = new URL(req.url);

    // Proxy API requests to backend
    if (
      url.pathname.startsWith("/mission") ||
      url.pathname.startsWith("/config")
    ) {
      try {
        return await fetch(`${BACKEND}${url.pathname}${url.search}`, {
          method: req.method,
          headers: req.headers,
          body: req.body,
        });
      } catch {
        return new Response("Backend unavailable", { status: 502 });
      }
    }

    // Serve static files
    let path = url.pathname === "/" ? "/index.html" : url.pathname;
    const file = Bun.file("." + path);
    if (await file.exists()) return new Response(file);

    // SPA fallback
    return new Response(Bun.file("./index.html"));
  },
});

console.log(`[dev] http://localhost:${server.port}  (backend proxy → ${BACKEND})`);

// Watch source and rebuild on change
watch("./src", { recursive: true }, async (_event, filename) => {
  console.log(`[watch] ${filename} changed`);
  await build();
});
