import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

// D-072: B2B ON Government na página pública de preços (vinda do catálogo central), acessível pela página
// inicial, sem "/mês", com o Professional recomendado e sem estourar a largura em celular/tablet.
const TAMANHOS = [
  { nome: "desktop", width: 1280, height: 900 },
  { nome: "tablet", width: 820, height: 1180 },
  { nome: "celular", width: 390, height: 844 },
];

for (const tamanho of TAMANHOS) {
  test(`B2B ON Government na página de preços (${tamanho.nome})`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: tamanho.width,
      height: tamanho.height,
    });
    await page.goto("/login");
    await page.getByTestId("link-planos").click();
    await expect(page).toHaveURL(/\/planos$/);

    const secao = page.getByTestId("secao-governo");
    await expect(
      secao.getByText("B2B ON Government", { exact: true }),
    ).toBeVisible();
    const ofertas = secao.getByTestId("oferta-governo");
    await expect(ofertas).toHaveCount(3);
    const professional = ofertas.filter({
      hasText: "B2B ON Government Professional",
    });
    await expect(professional.getByText("Recomendado")).toBeVisible();
    await expect(professional.getByText("R$ 120.000,00")).toBeVisible();
    await expect(professional.getByText("R$ 176.000,00")).toBeVisible();
    await expect(
      professional.getByText("600.000 AI Credits/ano"),
    ).toBeVisible();
    await expect(
      ofertas.filter({ hasText: "Department" }).getByText("R$ 108.000,00"),
    ).toBeVisible();
    await expect(
      ofertas.filter({ hasText: "Enterprise" }).getByText("R$ 264.000,00"),
    ).toBeVisible();
    // D-075 (OI-024): entitlements do catálogo central
    const entProfessional = professional.getByTestId("entitlements-governo");
    await expect(entProfessional.getByText("Usuários internos")).toBeVisible();
    await expect(
      entProfessional.getByText("50", { exact: true }),
    ).toBeVisible();
    await expect(
      ofertas
        .filter({ hasText: "Enterprise" })
        .getByTestId("entitlements-governo")
        .getByText("2 TB"),
    ).toBeVisible();
    await expect(secao.getByText(/\/mês/)).toHaveCount(0);
    await expect(
      secao.getByText(
        "Contratação inicial = Licença Institucional + Implantação + Subscrição Anual",
      ),
    ).toBeVisible();

    const larguras = await page.evaluate(() => [
      document.documentElement.scrollWidth,
      window.innerWidth,
    ]);
    expect(larguras[0]).toBeLessThanOrEqual(larguras[1]);
  });
}

test.describe("Admin", () => {
  test.use({ storageState: SESSAO });

  test("Admin → Planos mostra as ofertas Government no catálogo central", async ({
    page,
  }) => {
    await entrarLogado(page);
    await page.goto("/admin/planos");
    const tabela = page.getByTestId("tabela-governo");
    await expect(tabela.getByTestId("linha-governo")).toHaveCount(3);
    const professional = tabela
      .getByTestId("linha-governo")
      .filter({ hasText: "Professional" });
    await expect(professional.getByText("R$ 36.000,00")).toBeVisible();
    await expect(professional.getByText("R$ 176.000,00")).toBeVisible();
    await expect(professional.getByText("600.000/ano")).toBeVisible();
    await expect(professional.getByText(/Usuários internos: 50/)).toBeVisible();
    // D-075: perfis tributários iniciais do PO; sem custo de infraestrutura nem câmbio, a tela mostra o que falta
    await page.goto("/admin/parametros-financeiros");
    await expect(page.getByTestId("perfil-tributario")).toHaveCount(3);
    await expect(
      page
        .getByTestId("parametros-pendentes")
        .getByText(
          "Infrastructure Cost Model (custos reais de infraestrutura)",
        ),
    ).toBeVisible();
    await expect(
      page.getByTestId("cambio").getByText(/AWAITING_FX_RATE/),
    ).toBeVisible();
    await expect(page.getByTestId("waterfall-comissoes")).toBeVisible();
    await page.goto("/admin/governo");
    await expect(
      page.getByTestId("metricas-governo").getByText("ARR Government"),
    ).toBeVisible();
  });
});
