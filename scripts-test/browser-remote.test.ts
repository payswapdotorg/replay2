/* Standalone live test of the E2B desktop + Chrome + CDP browser tier.
   Run: . ../../scripts/env.sh && npx tsx scripts-test/browser-remote.test.ts */
import { browserRemoteAction, browserRemoteAvailable } from "../src/agent/browserRemote";

async function main() {
  console.log("available:", browserRemoteAvailable());
  const t0 = Date.now();
  let r = await browserRemoteAction({ action: "status" });
  console.log(`[status ${(Date.now() - t0) / 1000}s]`, r.content, "\n");

  const t1 = Date.now();
  r = await browserRemoteAction({ action: "open", url: "example.com" });
  console.log(`[open ${(Date.now() - t1) / 1000}s]`, r.content, "\n");

  const t2 = Date.now();
  r = await browserRemoteAction({ action: "read" });
  console.log(`[read ${(Date.now() - t2) / 1000}s]`, r.content.slice(0, 400), "\n");

  const t3 = Date.now();
  r = await browserRemoteAction({ action: "elements" });
  console.log(`[elements ${(Date.now() - t3) / 1000}s]`, r.content.slice(0, 400), "\n");

  const t4 = Date.now();
  r = await browserRemoteAction({ action: "screenshot" });
  console.log(`[screenshot ${(Date.now() - t4) / 1000}s]`, r.content, "| image bytes:", r.images?.[0]?.length || 0, "\n");

  const t5 = Date.now();
  r = await browserRemoteAction({ action: "click", fx: 0.5, fy: 0.5 });
  console.log(`[click ${(Date.now() - t5) / 1000}s]`, r.content, "\n");

  // heavier page: search on duckduckgo and type
  r = await browserRemoteAction({ action: "open", url: "https://duckduckgo.com" });
  console.log("[open ddg]", r.content, "\n");
  r = await browserRemoteAction({ action: "elements" });
  console.log("[elements ddg]", r.content.split("\n").slice(0, 6).join("\n"), "\n");
  r = await browserRemoteAction({ action: "click", fx: 0.5, fy: 0.14 });
  console.log("[click searchbox]", r.content);
  r = await browserRemoteAction({ action: "type", text: "z.ai glm" });
  console.log("[type]", r.content);
  r = await browserRemoteAction({ action: "press", key: "enter" });
  console.log("[enter]", r.content, "\n");
  await new Promise((res) => setTimeout(res, 2500));
  r = await browserRemoteAction({ action: "read" });
  console.log("[read results]", r.content.slice(0, 600), "\n");
  r = await browserRemoteAction({ action: "screenshot" });
  console.log("[screenshot after search] image bytes:", r.images?.[0]?.length || 0);
}

main().catch((e) => {
  console.error("TEST FAILED:", e);
  process.exit(1);
});
