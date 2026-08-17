import { execFileSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");
const DATABASE_URL = "sqlite:///./e2e_test.db";

// Banco do E2E é descartável de propósito — apaga antes de cada execução
// pra cada rodada começar do zero (sem ICP/conta/negócio acumulado de
// execuções anteriores poluindo os testes), e semeia o tenant/usuário
// fixos ANTES de subir os webServers — rodar isso encadeado dentro do
// próprio comando do webServer (`seed.py && uvicorn`) tirava a garantia
// de que as duas etapas rodam com o mesmo cwd/ambiente de forma síncrona.
export default function globalSetup(): void {
  for (const suffix of ["", "-wal", "-shm"]) {
    const arquivo = path.join(repoRoot, `e2e_test.db${suffix}`);
    if (existsSync(arquivo)) rmSync(arquivo);
  }

  execFileSync("python", [path.join("frontend", "e2e", "seed.py")], {
    cwd: repoRoot,
    env: { ...process.env, DATABASE_URL },
    stdio: "inherit",
  });
}
