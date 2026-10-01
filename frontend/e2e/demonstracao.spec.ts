import { expect, test } from "@playwright/test";

// D-082: link público da demonstração — sem login, abre um ambiente próprio já preenchido com dados fictícios.
test("Demonstração: abre sem login, com faixa de aviso e dados fictícios", async ({ page }) => {
  await page.goto("/login");
  await page.getByTestId("link-demo").click();
  await expect(page.getByText("Ambiente de demonstração")).toBeVisible({ timeout: 20_000 });
  await page.goto("/crm");
  await expect(page.getByText(/Metalúrgica|Plásticos|Cerâmica/).first()).toBeVisible();
  await page.goto("/bids");
  await expect(page.getByText(/Pregão Eletrônico/).first()).toBeVisible();
  // a rede de empresas (dados de clientes reais) não aparece na demonstração
  await expect(page.getByRole("link", { name: /Rede Social/ })).toHaveCount(0);
});
