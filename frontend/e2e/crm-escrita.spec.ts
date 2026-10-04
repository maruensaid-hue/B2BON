import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

// D-087 — escrita no CRM do cliente: opt-in por capacidade, persistência e
// URL de webhook mostrada uma vez. Nenhuma chamada ao HubSpot real acontece
// aqui (só configuração; a fila é testada no backend).
test.describe("escrita no CRM do cliente", () => {
  test.use({ storageState: SESSAO });

  test("liga PREDATOR → CRM numa conexão HubSpot, persiste e gera webhook", async ({ page }) => {
    await entrarLogado(page);
    await page.goto("/admin/api");
    const hub = page.getByTestId("conexoes-crm");
    await expect(hub).toBeVisible();

    const nome = `HubSpot E2E ${Date.now()}`;
    const formulario = hub.locator("form").filter({ has: page.getByPlaceholder("Nome da conexão") }).last();
    await formulario.getByRole("combobox").selectOption("hubspot");
    await formulario.getByPlaceholder("Nome da conexão").fill(nome);
    await formulario.getByPlaceholder("Access token (Private App ou OAuth)").fill("pat-e2e-token");
    await formulario.getByRole("button", { name: "Conectar" }).click();
    await expect(hub.getByText("Conexão criada.")).toBeVisible();

    const cartao = hub.locator("div.rounded-lg").filter({ hasText: nome });
    await cartao.getByTestId("abrir-escrita").click();
    const painel = cartao.getByTestId("conexao-escrita");
    await expect(painel).toBeVisible();

    // opt-in: começa desligado; deduplicação (só leitura) começa ligada
    const predator = painel.getByTestId("escrita-predator");
    await expect(predator).not.toBeChecked();
    const salvou = page.waitForResponse((r) => r.url().includes("/escrita") && r.request().method() === "PUT" && r.status() === 200);
    await predator.check();
    await salvou;
    await expect(painel.getByText("Configuração salva.")).toBeVisible();
    await expect(painel.getByText("Onde criar o negócio")).toBeVisible();

    // persiste: fechar e abrir de novo lê do servidor
    await cartao.getByTestId("abrir-escrita").click();
    await cartao.getByTestId("abrir-escrita").click();
    await expect(cartao.getByTestId("escrita-predator")).toBeChecked();

    // webhook de entrada: URL secreta mostrada uma vez
    await cartao.getByRole("button", { name: "Gerar URL de webhook" }).click();
    await expect(cartao.getByTestId("webhook-url")).toContainText("/hub-integracoes/webhook/whin_");
    await expect(cartao.getByText("Nada enviado ainda.")).toBeVisible();
  });
});
