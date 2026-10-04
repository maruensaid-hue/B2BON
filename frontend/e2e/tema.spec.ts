import { expect, test } from "@playwright/test";

import { E2E_EMAIL, E2E_SENHA, entrarLogado, SESSAO } from "./helpers";

// D-086 — tema claro/escuro. O ícone mostra a AÇÃO: claro → 🌙 (ativar escuro); escuro → ☀️ (ativar claro).
test.describe("tema claro/escuro", () => {
  test.use({ storageState: SESSAO });

  test("alterna sem recarregar, persiste no refresh e no servidor, acessível por teclado", async ({ page }) => {
    await entrarLogado(page);
    const html = page.locator("html");
    const botao = page.getByTestId("theme-toggle");

    // padrão: claro, com 🌙 e rótulo da ação
    await expect(html).not.toHaveAttribute("data-theme", "dark");
    await expect(botao).toHaveText("🌙");
    await expect(botao).toHaveAttribute("aria-label", "Ativar modo escuro");
    await expect(botao).toHaveAttribute("title", "Ativar modo escuro");
    const fundoClaro = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);

    // clique → escuro, sem reload; tokens trocados (fundo do body muda)
    const gravou = page.waitForResponse((r) => r.url().endsWith("/auth/preferencia-tema") && r.status() === 200);
    await botao.click();
    await gravou;
    await expect(html).toHaveAttribute("data-theme", "dark");
    await expect(botao).toHaveText("☀️");
    await expect(botao).toHaveAttribute("aria-label", "Ativar modo claro");
    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe(fundoClaro);

    // refresh: abre direto no escuro (aplicado antes da pintura pelo index.html)
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "dark");
    expect(await page.evaluate(() => localStorage.getItem("b2bon.theme"))).toBe("dark");

    // teclado: Enter e Espaço
    await botao.focus();
    await page.keyboard.press("Enter");
    await expect(html).toHaveAttribute("data-theme", "light");
    await expect(botao).toHaveText("🌙");
    await page.keyboard.press("Space");
    await expect(html).toHaveAttribute("data-theme", "dark");

    // cartões, tabelas, campos e modal respondem ao tema (fundo escuro)
    const fundo = (seletor: string) =>
      page.locator(seletor).first().evaluate((el) => `${el.tagName}.${el.className} ${getComputedStyle(el).backgroundColor}`);
    const escuro = async (seletor: string) => {
      const info = await fundo(seletor);
      const m = info.slice(info.lastIndexOf("rgb")).match(/\d+/g)!.map(Number);
      expect((0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255, info).toBeLessThan(0.3);
      return true;
    };
    await page.goto("/admin/tenants");
    await expect(page.getByRole("table")).toBeVisible();
    expect(await escuro("main .rounded-2xl, main [class*='bg-surf']")).toBe(true);
    await page.getByRole("button", { name: "+ Criar tenant" }).click();
    expect(await escuro("[role='dialog']")).toBe(true);
    expect(await escuro("[role='dialog'] input")).toBe(true);
    await page.keyboard.press("Escape");

    // volta ao claro para não afetar as demais specs (a preferência fica no usuário E2E)
    await botao.click();
    await expect(html).toHaveAttribute("data-theme", "light");
  });

  test("transição curta na troca, e nenhuma com prefers-reduced-motion", async ({ page }) => {
    await entrarLogado(page);
    const duracaoDuranteTroca = async () => {
      await page.getByTestId("theme-toggle").click();
      return page.evaluate(() => getComputedStyle(document.body).transitionDuration);
    };
    expect(await duracaoDuranteTroca()).toContain("0.2s");
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(parseFloat(await duracaoDuranteTroca())).toBeLessThan(0.01);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });

  test("no celular o seletor continua visível no cabeçalho", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await entrarLogado(page);
    const botao = page.getByTestId("theme-toggle");
    await expect(botao).toBeVisible();
    const caixa = (await botao.boundingBox())!;
    expect(caixa.y).toBeLessThan(80); // topo
    expect(caixa.x + caixa.width).toBeGreaterThan(390 - 80); // canto direito
    await botao.click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await botao.click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });
});

test("a escolha volta num navegador limpo, pelo login (preferência do usuário no servidor)", async ({ page, browser }) => {
  // grava "escuro" no usuário com uma sessão existente
  const contexto = await browser.newContext({ storageState: SESSAO });
  const sessao = await contexto.newPage();
  await entrarLogado(sessao);
  await sessao.getByTestId("theme-toggle").click();
  await expect(sessao.locator("html")).toHaveAttribute("data-theme", "dark");
  await contexto.close();

  // navegador sem nada salvo: abre claro, faz login e o escuro do usuário é aplicado
  await page.goto("/login");
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", "dark");
  await page.getByPlaceholder("voce@empresa.com.br").fill(E2E_EMAIL);
  await page.getByPlaceholder("••••••••").fill(E2E_SENHA);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  // limpa para as demais specs
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});
