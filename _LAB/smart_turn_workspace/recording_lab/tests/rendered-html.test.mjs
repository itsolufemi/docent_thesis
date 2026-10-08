import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the Smart Turn recording lab", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Smart Turn Human Recording Lab<\/title>/i);
  assert.match(html, /Human turn-recording study/);
  assert.match(html, /40 utterances/);
  assert.match(html, /Benchmark assets/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
});

test("defines a balanced forty-prompt human suite", async () => {
  const source = await readFile(
    new URL("../app/prompts.ts", import.meta.url),
    "utf8",
  );
  const identifiers = source.match(/id: "human_\d{2}_[^"]+"/g) ?? [];
  assert.equal(identifiers.length, 40);
  assert.match(source, /label: "complete" as const/);
  assert.match(source, /label: "incomplete" as const/);
});
