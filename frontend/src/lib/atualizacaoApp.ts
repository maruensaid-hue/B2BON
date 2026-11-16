// Versão nova publicada: o service worker guarda uma cópia de todas as telas, e sem isto uma aba aberta (ou o app instalado) seguia com a
// tela antiga por horas — visto em 16/11/2026, quando uma conta continuou sem o botão "Buscar no LinkedIn" já publicado. A versão nova é
// procurada a cada 10 minutos e quando a aba volta a ficar visível; depois de baixada, fica esperando e é aplicada (recarregando) só num
// momento seguro: aba escondida ou troca de tela, nunca no meio de um formulário que a pessoa está preenchendo.
// O service worker é gerado em modo "prompt" (vite.config.ts): a versão nova só assume quando recebe SKIP_WAITING daqui.
const INTERVALO_VERIFICACAO_MS = 10 * 60 * 1000;
const CHAVE_RECARGA_CHUNK = "b2bon.recarga-chunk";

let registro: ServiceWorkerRegistration | null = null;
let aplicando = false;

function versaoNovaEsperando(): ServiceWorker | null {
  // Sem controlador é o primeiro acesso: a versão instalada já é a atual, não há o que trocar.
  return registro?.waiting && navigator.serviceWorker.controller ? registro.waiting : null;
}

export function aplicarAtualizacaoPendente(): void {
  const nova = versaoNovaEsperando();
  if (!nova || aplicando) return;
  aplicando = true;
  navigator.serviceWorker.addEventListener("controllerchange", () => window.location.reload(), { once: true });
  nova.postMessage({ type: "SKIP_WAITING" });
}

function acompanharInstalacao(reg: ServiceWorkerRegistration): void {
  reg.addEventListener("updatefound", () => {
    const instalando = reg.installing;
    instalando?.addEventListener("statechange", () => {
      if (instalando.state === "installed" && document.visibilityState === "hidden") aplicarAtualizacaoPendente();
    });
  });
}

if ("serviceWorker" in navigator) {
  void navigator.serviceWorker.ready.then((reg) => {
    registro = reg;
    acompanharInstalacao(reg);
    const verificar = () => {
      if (navigator.onLine) reg.update().catch(() => undefined);
    };
    window.setInterval(verificar, INTERVALO_VERIFICACAO_MS);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") verificar();
      else aplicarAtualizacaoPendente();
    });
  });
}

// Tela carregada sob demanda que sumiu do servidor depois de uma publicação: recarrega uma vez para buscar a versão nova.
window.addEventListener("vite:preloadError", (evento) => {
  try {
    if (sessionStorage.getItem(CHAVE_RECARGA_CHUNK)) return;
    sessionStorage.setItem(CHAVE_RECARGA_CHUNK, "1");
  } catch {
    return;
  }
  evento.preventDefault();
  window.location.reload();
});
window.addEventListener("load", () => {
  window.setTimeout(() => {
    try {
      sessionStorage.removeItem(CHAVE_RECARGA_CHUNK);
    } catch {
      /* sem armazenamento: nada a limpar */
    }
  }, 10_000);
});
