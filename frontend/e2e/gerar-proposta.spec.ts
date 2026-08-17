import { expect, test } from "@playwright/test";

import { E2E_EMAIL, E2E_SENHA, login } from "./helpers";

const API_BASE = "http://localhost:8000/api/v1";

/** Prepara uma oportunidade via API (não é o que este teste verifica —
 * só a pré-condição) para focar a checagem no fluxo de gerar proposta. */
async function seedNegocio(request: import("@playwright/test").APIRequestContext): Promise<string> {
  const login = await request.post(`${API_BASE}/auth/login`, {
    data: { email: E2E_EMAIL, senha: E2E_SENHA },
  });
  const { access_token: token } = await login.json();
  const headers = { Authorization: `Bearer ${token}` };

  const icp = await (
    await request.post(`${API_BASE}/icp`, {
      headers,
      data: { nome: "ICP E2E", segmento: "Tecnologia", porte: "PEQUENO", regiao: "SP" },
    })
  ).json();

  const conta = await (
    await request.post(`${API_BASE}/icp/${icp.id}/contas`, {
      headers,
      data: { nome: `Conta E2E ${Date.now()}` },
    })
  ).json();

  const decisor = await (
    await request.post(`${API_BASE}/contas/${conta.id}/decisores`, {
      headers,
      data: { nome: "Decisor E2E" },
    })
  ).json();

  await request.post(`${API_BASE}/crm/negocios`, {
    headers,
    data: { conta_id: conta.id, decisor_id: decisor.id, nome: "Negócio para proposta E2E", valor: 1000 },
  });

  return token;
}

test("gera proposta em PDF para uma oportunidade e confirma sucesso na tela", async ({ page, request }) => {
  await seedNegocio(request);
  await login(page);

  await page.goto("/crm/propostas/nova");
  await expect(page.getByText("Gera uma nova versão de proposta em PDF")).toBeVisible();

  // Única oportunidade cadastrada neste tenant de teste — a opção 0 é o
  // placeholder "Selecione a oportunidade".
  await page.getByRole("combobox").selectOption({ index: 1 });

  await expect(page.getByText("Itens desta proposta")).toBeVisible();
  await page.getByRole("button", { name: "Gerar e anexar proposta" }).click();

  await expect(page.getByText(/Proposta v\d+ gerada com sucesso\./)).toBeVisible();
  await expect(page.getByRole("button", { name: "Baixar PDF" })).toBeVisible();
});
