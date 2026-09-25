import { expect, test } from "@playwright/test";

// Fase 14: página pública mostra o catálogo vindo do backend; produto sem
// preço definido (Public Procurement) nunca aparece como contratável.
test("página de planos mostra o catálogo sem vender o que não foi lançado", async ({
  page,
}) => {
  await page.goto("/planos");
  const catalogo = page.getByTestId("catalogo-produtos");
  await expect(catalogo.getByText("Todos os produtos B2B ON")).toBeVisible();

  const procurement = catalogo.locator("div.rounded-xl", {
    hasText: "Public Procurement",
  });
  await expect(
    procurement.getByText("Em breve · preço em definição"),
  ).toBeVisible();
  await expect(procurement.getByRole("link", { name: /Assin/ })).toHaveCount(0);
  await expect(procurement.getByText(/R\$/)).toHaveCount(0);

  await expect(
    catalogo
      .locator("div.rounded-xl", { hasText: "Bid Intelligence" })
      .getByText("Sob consulta"),
  ).toBeVisible();
  // preços existentes continuam na página
  await expect(page.getByText("R$ 924,50")).toBeVisible();
});

// Fase 15: pacotes de AI Credits vêm da API (catálogo versionado); a
// franquia do Public Procurement aparece como em definição, sem número.
test("planos e explicação mostram AI Credits vindos do catálogo", async ({
  page,
}) => {
  await page.goto("/planos");
  await expect(page.getByText("B2B ON AI Credits")).toBeVisible();
  await expect(page.getByText("AI 1M", { exact: true })).toBeVisible();
  await expect(page.getByText("Falar com vendas").first()).toBeVisible();

  await page.goto("/como-funcionam-ai-credits");
  await expect(
    page.getByRole("heading", { name: "Como funcionam os AI Credits" }),
  ).toBeVisible();
  await expect(page.getByText("Os créditos do plano acumulam?")).toBeVisible();
  const procurement = page.locator("div.rounded-xl", {
    hasText: "Public Procurement",
  });
  await expect(procurement.getByText("Em definição")).toBeVisible();
});
