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

// Fase 15: AI Credits em cards (como funciona, incluídos, pacotes e consumo
// por operação), vindos da API; Public Procurement aparece em definição.
test("planos e explicação mostram AI Credits em cards vindos do catálogo", async ({
  page,
}) => {
  await page.goto("/planos");
  const cards = page.getByTestId("ai-credits-cards");
  await expect(cards.getByText("B2B ON AI Credits")).toBeVisible();
  await expect(cards.getByText("Os créditos do plano acumulam?")).toBeVisible();
  await expect(cards.getByText("AI 1M", { exact: true })).toBeVisible();
  await expect(cards.getByText("Quanto cada operação consome")).toBeVisible();
  const procurement = cards.locator("div.rounded-xl", {
    hasText: "Public Procurement",
  });
  await expect(procurement.getByText("Em definição")).toBeVisible();

  await page.goto("/como-funcionam-ai-credits");
  await expect(
    page.getByRole("heading", { name: "Como funcionam os AI Credits" }),
  ).toBeVisible();
  await expect(
    page.getByTestId("ai-credits-cards").getByText("Pacotes adicionais"),
  ).toBeVisible();
});
