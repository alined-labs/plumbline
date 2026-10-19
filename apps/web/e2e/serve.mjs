// A dependency-free static server for the export in out/, used by Playwright and
// Lighthouse: `node e2e/serve.mjs <dir> <port>`. trailingSlash routes map to index.html.
import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";

const root = resolve(process.argv[2] ?? "out");
const port = Number(process.argv[3] ?? 3100);
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
  ".woff2": "font/woff2",
};

function fileFor(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath.split("?")[0])).replace(/^(\.\.[/\\])+/, "");
  let file = join(root, clean);
  if (!file.startsWith(root)) return null;
  try {
    if (statSync(file).isDirectory()) file = join(file, "index.html");
    statSync(file);
    return file;
  } catch {
    return null;
  }
}

createServer((req, res) => {
  const file = fileFor(req.url ?? "/") ?? fileFor("/404.html");
  if (!file) {
    res.writeHead(404).end("Not found");
    return;
  }
  res.writeHead(file.endsWith("404.html") && !req.url?.startsWith("/404") ? 404 : 200, {
    "content-type": types[extname(file)] ?? "application/octet-stream",
  });
  createReadStream(file).pipe(res);
}).listen(port, "127.0.0.1", () => console.log(`serving ${root} on http://127.0.0.1:${port}`));
