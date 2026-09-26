import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

test.use({ storageState: SESSAO });

// Phase H: o detalhe de risco do MAP virou um componente só (contas e
// tenants). O usuário do E2E é super_admin, então /map abre a saúde dos
// tenants assinantes — o mesmo componente da tela de contas.
test("MAP: detalhe de risco do tenant e registro de interação", async ({ page }) => {
  await entrarLogado(page);
  await page.goto("/map");
  await page.getByRole("cell", { name: "e2e-playwright" }).click();
  await expect(page.getByText(/^Detalhe — /)).toBeVisible();
  await expect(page.getByText(/\/100/)).toBeVisible();

  await page.getByRole("button", { name: "Registrar interação" }).click();
  await page.locator('select[name="tipo"]').selectOption("feedback_positivo");
  const descricao = `Elogiou o suporte ${Date.now()}`;
  await page.locator('input[name="descricao"]').fill(descricao);
  await page.getByRole("button", { name: "Registrar", exact: true }).click();
  await expect(page.getByText(`— ${descricao}`)).toBeVisible();
});
