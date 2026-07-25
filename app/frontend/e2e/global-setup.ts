/**
 * Warm the Render-hosted backend before the suite: the free tier spins down
 * after inactivity, and the first question would otherwise eat the whole
 * expect timeout on a cold start.
 */
const API = process.env.E2E_API_URL ?? "https://docuchat-api-odw2.onrender.com";

export default async function globalSetup(): Promise<void> {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${API}/health`);
      if (res.ok) return;
    } catch {
      // still waking up
    }
    await new Promise((r) => setTimeout(r, 3_000));
  }
  throw new Error(`Backend at ${API} did not become healthy within 120s`);
}
