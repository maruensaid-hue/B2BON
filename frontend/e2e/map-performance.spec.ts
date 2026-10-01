import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

test.use({ storageState: SESSAO });

// D-080: o gestor (super_admin) abre a Performance Comercial no MAP — Daily, equipe e a configuração versionada com as
// quotas do PO (R$ 7.500 por representante em Out/26, pipeline alvo R$ 30.000).
test("MAP Performance: Daily, equipe e quotas configuradas", async ({ page }) => {
  await entrarLogado(page);
  await page.goto("/map");
  await page.getByRole("button", { name: "Performance comercial" }).click();
  await expect(page.getByText("Quota da equipe")).toBeVisible();
  await page.getByRole("button", { name: "Equipe" }).click();
  await expect(page.getByText("Comparação por attainment e indicadores operacionais")).toBeVisible();
  await page.getByRole("button", { name: "Configuração" }).click();
  // D-081: prontidão — o que falta configurar (time de tamanho variável, vínculo, ofertas, contato efetivo)
  await expect(page.getByText("Prontidão")).toBeVisible();
  await expect(page.getByText("Confirmar o critério de contato efetivo")).toBeVisible();
  const linha = page.getByRole("row").filter({ hasText: "2026-10" }).first();
  await expect(linha).toContainText("R$ 7.500");
  await expect(linha).toContainText("R$ 30.000");
});
