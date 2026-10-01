import { expect, test } from "@playwright/test";

import { entrarLogado, SESSAO } from "./helpers";

test.use({ storageState: SESSAO });

// Tutoriais dos módulos de licitações e compras: abrem pelo "Rever tutorial",
// percorrem os passos e fecham ("Concluir").
const MODULOS = [
  { rota: "/bids", primeiro: "Licitações em acompanhamento", passos: 5 },
  { rota: "/compras", primeiro: "Indicadores do órgão", passos: 5 },
  { rota: "/sourcing", primeiro: "Novo processo de compra", passos: 4 },
  {
    rota: "/convites-compra",
    primeiro: "Convites de compra recebidos",
    passos: 2,
  },
];

test("tutoriais de Licitações, Compras, Sourcing e Convites", async ({
  page,
}) => {
  await entrarLogado(page);
  for (const { rota, primeiro, passos } of MODULOS) {
    await page.goto(rota);
    await page.getByRole("button", { name: "🔄 Rever tutorial" }).click();
    await expect(page.getByText(primeiro, { exact: true })).toBeVisible();
    for (let i = 1; i < passos; i++) {
      await page.getByRole("button", { name: "Próximo →" }).click();
    }
    await page.getByRole("button", { name: "Concluir" }).click();
    await expect(page.getByRole("button", { name: "Concluir" })).toHaveCount(0);
  }
});
