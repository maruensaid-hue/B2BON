import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

test.use({ storageState: SESSAO });

// Phase C: workspace compartilhado com abas; o andamento vem do workflow
// (a negociação só aparece depois da proposta enviada, no Enterprise Bid) e a
// aba de proposta monta o esboço sem IA.
test("enterprise bid: abas, andamento pelo workflow e esboço de proposta", async ({
  page,
}) => {
  await entrarLogado(page);
  await page.goto("/bids");
  await page
    .getByPlaceholder("Título / número do edital")
    .fill("RFQ ACME 2026");
  await page.getByPlaceholder("Órgão / comprador").fill("ACME S.A.");
  await page.locator('select[name="modalidade"]').selectOption("PRIVATE_RFQ");
  await page.getByRole("button", { name: "Cadastrar" }).click();
  await page.getByRole("link", { name: /RFQ ACME 2026/ }).click();

  const workspace = page.getByTestId("bid-workspace");
  await expect(workspace.getByRole("tab")).toHaveText([
    "Visão geral",
    "Documentos",
    "Requisitos",
    "Conformidade",
    "Proposta",
  ]);
  await expect(
    workspace.getByRole("button", { name: "Em negociação" }),
  ).toHaveCount(0);
  await workspace.getByRole("button", { name: "Proposta enviada" }).click();
  await expect(
    workspace.getByText("Status atual Proposta enviada"),
  ).toBeVisible();
  await workspace.getByRole("button", { name: "Em negociação" }).click();
  await expect(workspace.getByText("Status atual Em negociação")).toBeVisible();

  await workspace.getByRole("tab", { name: "Proposta" }).click();
  await expect(page).toHaveURL(/aba=proposta/);
  const proposta = page.getByTestId("proposta-aba");
  await expect(
    proposta.getByText(
      "Sem requisitos: confirme os requisitos para montar a proposta.",
    ),
  ).toBeVisible();
  await expect(proposta.getByText(/nenhum \(C0\)/)).toBeVisible();
});
