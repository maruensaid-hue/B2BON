import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

test.use({ storageState: SESSAO });

test("cria negócio para cliente novo direto no Kanban, o card aparece no board e a tela completa traz a inteligência", async ({ page }) => {
  await entrarLogado(page);
  await page.goto("/crm");
  await expect(page.getByText("CRM — Pipeline")).toBeVisible();

  await page.getByRole("button", { name: "+ Novo negócio" }).click();
  await page.getByRole("button", { name: "Cadastrar cliente novo" }).click();
  await page.getByRole("checkbox", { name: "Sem ICP (lead avulso — indicação, evento, contato pessoal)" }).check();

  const nomeCliente = `Cliente E2E ${Date.now()}`;
  await page.getByPlaceholder("Nome do cliente").fill(nomeCliente);
  await page.getByPlaceholder("Nome do contato").fill("Contato E2E");
  const nomeNegocio = `Negócio criado pelo E2E ${Date.now()}`;
  await page.getByPlaceholder("Ex: Licença Professional — 12 meses").fill(nomeNegocio);
  await page.getByPlaceholder("0,00").fill("5000");

  await page.getByRole("button", { name: "Criar negócio" }).click();

  // O modal fecha e o card com o nome da empresa recém-criada aparece
  // na coluna "Descoberta" (estágio inicial padrão).
  await expect(page.getByText(nomeCliente)).toBeVisible();
  await expect(page.getByText(nomeNegocio)).toBeVisible();

  // Fase 6: a tela completa do negócio traz o card de inteligência. Sem
  // necessidades registradas, o Next Best Offer declara o que falta em
  // vez de inventar; a necessidade dita pelo vendedor entra confirmada.
  // (No mesmo teste de propósito: o login tem rate limit por IP.)
  await page.getByRole("button", { name: nomeNegocio }).click();
  await page.getByRole("link", { name: "⤢ Abrir tela completa" }).click();
  const card = page.getByTestId("inteligencia-oportunidade");
  await expect(card.getByText("Inteligência da oportunidade")).toBeVisible();
  await expect(card.getByText("Informação insuficiente")).toBeVisible();
  await expect(card.getByText("Envolver o decisor")).toBeVisible();
  await card.getByPlaceholder("Necessidade dita pelo cliente").fill("Reduzir custo de licenças");
  await card.getByRole("button", { name: "Adicionar" }).click();
  await expect(card.getByText("Dor: Reduzir custo de licenças")).toBeVisible();
});
