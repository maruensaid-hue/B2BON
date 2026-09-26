import { expect, type Page } from "@playwright/test";

export const E2E_EMAIL = "e2e@teste.com.br";
export const E2E_SENHA = "SenhaE2E123!";

/** Login real pela tela — não injeta token: é o próprio fluxo de login
 * que a gente quer ver funcionando de verdade. */
export async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByPlaceholder("voce@empresa.com.br").fill(E2E_EMAIL);
  await page.getByPlaceholder("••••••••").fill(E2E_SENHA);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByText("Visão geral · CRM + MAP")).toBeVisible();
}

/** Sessão salva pelo `auth.setup.ts` (um login real pela tela, uma vez por
 * rodada). Specs que não testam o login reaproveitam: o /auth/login tem
 * rate limit por IP (5 tentativas/5min) e cada login a mais conta. */
export const SESSAO = "e2e/.auth/sessao.json";

export async function entrarLogado(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByText("Visão geral · CRM + MAP")).toBeVisible();
}
