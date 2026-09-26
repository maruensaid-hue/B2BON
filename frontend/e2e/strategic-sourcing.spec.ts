import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

test.use({ storageState: SESSAO });

// Phase E: RFQ do rascunho ao contrato pela tela — itens, convite, proposta
// com preço por item, comparação, aprovação humana e contrato.
test("RFQ: cotação, comparação, aprovação e contrato", async ({ page }) => {
  await entrarLogado(page);
  await page.getByRole("link", { name: "Strategic Sourcing" }).click();
  await page.locator('select[name="tipo_processo"]').selectOption("RFQ");
  await page
    .getByPlaceholder("Necessidade / título")
    .fill("Cadeiras ergonômicas");
  await page.getByRole("button", { name: "Criar" }).click();

  const ws = page.getByTestId("sourcing-workspace");
  // Phase G: próxima ação determinística vinda do servidor
  await expect(ws.getByTestId("proxima-acao")).toContainText(
    "Cadastre requisitos ou itens",
  );
  await ws.getByRole("tab", { name: "Itens e requisitos" }).click();
  await ws.getByPlaceholder("Item").fill("Cadeira ergonômica");
  await ws.getByPlaceholder("Qtd.").fill("10");
  await ws
    .locator("form", { has: page.getByPlaceholder("Item") })
    .getByRole("button", { name: "Adicionar" })
    .click();
  await expect(ws.getByText("Cadeira ergonômica · 10")).toBeVisible();

  await ws.getByRole("tab", { name: /Fornecedores/ }).click();
  await ws.getByPlaceholder("Convidar pelo nome").fill("Móveis Delta");
  await ws.getByRole("button", { name: "Convidar", exact: true }).click();
  await expect(ws.getByText("Móveis Delta")).toBeVisible();

  await ws.getByRole("tab", { name: "Visão geral" }).click();
  await ws.getByRole("button", { name: "Publicado" }).click();
  await ws.getByRole("button", { name: "Recebendo propostas" }).click();
  await expect(ws.getByText("Status Recebendo propostas")).toBeVisible();

  await ws.getByRole("tab", { name: /Propostas/ }).click();
  await ws.getByPlaceholder("Preço unit. Cadeira ergonômica").fill("850.5");
  await ws.getByRole("button", { name: "Registrar", exact: true }).click();
  await expect(ws.getByText("Móveis Delta · rodada 1")).toBeVisible();

  await ws.getByRole("tab", { name: "Comparação" }).click();
  await expect(ws.getByText("menor valor")).toBeVisible();
  await expect(
    ws.getByText("não há escolha automática de vencedor"),
  ).toBeVisible();

  await ws.getByRole("tab", { name: "Visão geral" }).click();
  await expect(ws.getByTestId("proxima-acao")).toContainText(
    "compare as propostas e solicite a aprovação",
  );
  await ws
    .getByPlaceholder("Justificativa da escolha")
    .fill("Único cotado dentro do prazo");
  await ws.getByRole("button", { name: "Solicitar aprovação" }).click();
  await ws.getByRole("button", { name: "Decidir (administrador)" }).click();
  await expect(ws.getByText("APROVADA")).toBeVisible();
  await ws.getByPlaceholder("Número do contrato").fill("CT-2026-01");
  await ws.getByRole("button", { name: "Registrar contrato" }).click();
  await expect(
    ws.getByText(/Contrato CT-2026-01 com Móveis Delta/),
  ).toBeVisible();
  await expect(ws.getByText("Status Contratado")).toBeVisible();
});
