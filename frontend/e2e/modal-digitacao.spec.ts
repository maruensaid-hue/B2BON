import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

// Bug real (2026-10-02): no campo de confirmação "Excluir tenant definitivamente" só entrava um caractere por vez — o
// Modal devolvia o foco ao contêiner a cada tecla. Digita tecla a tecla, como uma pessoa, e confere o texto inteiro.
test.use({ storageState: SESSAO });

test("campo dentro de modal aceita o texto inteiro digitado tecla a tecla", async ({ page }) => {
  await entrarLogado(page);
  await page.goto("/admin/tenants");
  await page.getByRole("button", { name: "Excluir definitivamente" }).first().click();

  const dialogo = page.getByRole("dialog");
  const identificador = (await dialogo.locator("b").last().textContent())?.trim() ?? "";
  expect(identificador.length).toBeGreaterThan(3);

  const campo = dialogo.getByPlaceholder(identificador);
  await campo.click();
  await campo.pressSequentially(identificador, { delay: 30 });

  await expect(campo).toHaveValue(identificador);
  await expect(campo).toBeFocused();
  await expect(dialogo.getByRole("button", { name: "Excluir definitivamente" })).toBeEnabled();
  await page.keyboard.press("Escape"); // fecha sem excluir
  await expect(dialogo).toHaveCount(0);
});
