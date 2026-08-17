import { expect, test } from "@playwright/test";

import { E2E_EMAIL, login } from "./helpers";

test("login com credenciais válidas leva ao Dashboard", async ({ page }) => {
  await login(page);
  await expect(page.getByText("Visão geral · CRM + MAP")).toBeVisible();
});

test("login com senha errada mostra mensagem de erro e não navega", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("voce@empresa.com.br").fill(E2E_EMAIL);
  await page.getByPlaceholder("••••••••").fill("senha-errada-de-proposito");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();

  await expect(page.getByText("E-mail ou senha inválidos.")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});
