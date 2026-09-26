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

  // Phase I (D-059): Bid Intelligence com preço aprovado passa a ser contratável
  await expect(
    catalogo
      .locator("div.rounded-xl", { hasText: "Bid Intelligence" })
      .first()
      .getByText("Disponível"),
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

// Phase I (D-059): produtos por job-to-be-done com os preços aprovados vindos
// do catálogo; "a partir de" vai para o comercial; o que não tem preço não
// mostra valor nem botão de compra.
test("página de vendas mostra os produtos com os preços aprovados", async ({
  page,
}) => {
  await page.goto("/planos");
  const linhas = page.getByTestId("linhas-comerciais");
  const bids = linhas.getByTestId("linha-bid_intelligence");
  await expect(bids.getByText("R$ 1.490,00")).toBeVisible();
  await expect(bids.getByText(/25\.000 créditos/)).toBeVisible();
  // Phase J3 (OI-023): 10 usuários incluídos; usuário adicional sem preço
  await expect(bids.getByText(/até 10 usuários/)).toBeVisible();
  await expect(
    bids.getByText("Usuário adicional: preço em definição"),
  ).toBeVisible();

  const sourcing = linhas.getByTestId("linha-strategic_sourcing");
  await expect(sourcing.getByText("R$ 2.990,00")).toBeVisible();
  await expect(sourcing.getByText(/até 5 usuários/)).toBeVisible();
  const enterprise = sourcing.getByTestId("plano-da-linha").filter({
    hasText: "Strategic Sourcing Enterprise",
  });
  await expect(enterprise.getByText("a partir de")).toBeVisible();
  await expect(enterprise.getByText("R$ 5.990,00")).toBeVisible();
  await expect(
    enterprise.getByRole("link", { name: /Falar com o comercial/ }),
  ).toBeVisible();
  await expect(enterprise.getByRole("link", { name: /Assinar/ })).toHaveCount(
    0,
  );

  for (const pendente of ["linha-public_procurement", "linha-suite"]) {
    const linha = linhas.getByTestId(pendente);
    await expect(linha.getByText("Preço em definição")).toBeVisible();
    await expect(linha.getByText(/R\$/)).toHaveCount(0);
    await expect(linha.getByRole("link", { name: /Assinar/ })).toHaveCount(0);
  }

  await sourcing
    .getByTestId("plano-da-linha")
    .filter({ hasText: "R$ 2.990,00" })
    .getByRole("link", { name: /Assinar/ })
    .click();
  await expect(page).toHaveURL(/criar-conta\?plano=Strategic/);
});
