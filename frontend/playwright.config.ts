import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");

// Banco isolado, só para o E2E — nunca o predator.db de desenvolvimento
// (o .gitignore raiz já cobre *.db). app/main.py cria as tabelas sozinho
// na subida (SQLite, idempotente) — sem precisar rodar Alembic aqui.
const DATABASE_URL = "sqlite:///./e2e_test.db";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  // Sequencial de propósito: todos os testes batem no mesmo backend e no
  // mesmo /auth/login, que tem rate limit por IP (5 tentativas/5min,
  // proteção contra força bruta) — rodar em paralelo derruba os próprios
  // testes por excesso de tentativas de login vindas do mesmo IP.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "python -m uvicorn app.main:app --port 8000",
      cwd: repoRoot,
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      env: { DATABASE_URL },
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      cwd: __dirname,
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
