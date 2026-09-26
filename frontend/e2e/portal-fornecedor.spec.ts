import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

test.use({ storageState: SESSAO });

// Phase F: o comprador gera o link; o fornecedor, sem login, abre o convite,
// pergunta e envia a proposta; o comprador recebe pelo portal.
test("fornecedor responde pelo link, sem login", async ({ page, browser }) => {
  await entrarLogado(page);
  await page.goto("/sourcing");
  await page
    .getByPlaceholder("Necessidade / título")
    .fill("Serviço de limpeza");
  await page.getByRole("button", { name: "Criar" }).click();
  const ws = page.getByTestId("sourcing-workspace");
  await ws.getByRole("tab", { name: "Requisitos" }).click();
  await ws
    .getByPlaceholder("Requisito ou pergunta")
    .fill("Equipe de 10 pessoas");
  await ws.getByRole("button", { name: "Adicionar" }).click();
  await ws.getByRole("tab", { name: /Fornecedores/ }).click();
  await ws.getByPlaceholder("Convidar pelo nome").fill("Limpa Tudo");
  await ws.getByRole("button", { name: "Convidar", exact: true }).click();
  await ws.getByRole("tab", { name: "Visão geral" }).click();
  await ws.getByRole("button", { name: "Publicado" }).click();
  await ws.getByRole("button", { name: "Recebendo propostas" }).click();
  await expect(ws.getByText("Status Recebendo propostas")).toBeVisible();
  await ws.getByRole("tab", { name: /Fornecedores/ }).click();
  await ws.getByRole("button", { name: "Link de acesso" }).click();
  const link = (await ws.getByTestId("link-acesso").textContent()) ?? "";
  expect(link).toContain("/portal-fornecedor#");

  const fornecedor = await (await browser.newContext()).newPage(); // sem sessão
  await fornecedor.goto(link);
  const portal = fornecedor.getByTestId("portal-fornecedor");
  await expect(portal.getByText("Serviço de limpeza")).toBeVisible();
  await expect(portal.getByText("Equipe de 10 pessoas")).toBeVisible();
  await portal
    .getByPlaceholder("Sua pergunta ao comprador")
    .fill("Inclui materiais?");
  await portal.getByRole("button", { name: "Perguntar" }).click();
  await expect(portal.getByText("Pergunta enviada.")).toBeVisible();
  await portal.getByPlaceholder("Valor total").fill("12000");
  await portal.getByRole("button", { name: "Enviar proposta" }).click();
  await expect(
    portal.getByText("Proposta enviada ao comprador."),
  ).toBeVisible();
  await expect(portal.getByText(/Rodada 1/)).toBeVisible();

  await page.reload();
  await ws.getByRole("tab", { name: /Propostas/ }).click();
  await expect(ws.getByText(/enviada pelo fornecedor/)).toBeVisible();
  await ws.getByRole("tab", { name: /Fornecedores/ }).click();
  await expect(ws.getByText("Inclui materiais?")).toBeVisible();
});
