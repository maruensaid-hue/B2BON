import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("cria negócio para cliente novo direto no Kanban e o card aparece no board", async ({ page }) => {
  await login(page);
  await page.goto("/crm");
  await expect(page.getByText("CRM — Pipeline")).toBeVisible();

  await page.getByRole("button", { name: "+ Novo negócio" }).click();
  await page.getByRole("button", { name: "Cadastrar cliente novo" }).click();
  await page.getByRole("checkbox", { name: "Sem ICP (lead avulso — indicação, evento, contato pessoal)" }).check();

  const nomeCliente = `Cliente E2E ${Date.now()}`;
  await page.getByPlaceholder("Nome do cliente").fill(nomeCliente);
  await page.getByPlaceholder("Nome do contato").fill("Contato E2E");
  await page.getByPlaceholder("Ex: Licença Professional — 12 meses").fill("Negócio criado pelo E2E");
  await page.getByPlaceholder("0,00").fill("5000");

  await page.getByRole("button", { name: "Criar negócio" }).click();

  // O modal fecha e o card com o nome da empresa recém-criada aparece
  // na coluna "Descoberta" (estágio inicial padrão).
  await expect(page.getByText(nomeCliente)).toBeVisible();
  await expect(page.getByText("Negócio criado pelo E2E")).toBeVisible();
});
