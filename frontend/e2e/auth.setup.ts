import { test as setup } from "@playwright/test";

import { login, SESSAO } from "./helpers";

// Um login real pela tela por rodada; a sessão fica em SESSAO para as specs
// que só precisam estar logadas (o login em si é testado em login.spec.ts).
setup("autenticar", async ({ page }) => {
  await login(page);
  await page.context().storageState({ path: SESSAO });
});
