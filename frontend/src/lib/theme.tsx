import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { useAuth } from "@/lib/auth";
import { ThemeContext, type ThemeMode } from "@/lib/themeContext";

/** D-086 — tema da interface. Um único mecanismo: o atributo `data-theme` no <html> troca os tokens semânticos de
 * `index.css` (nenhum componente escolhe cor por tema). O script do `index.html` aplica a escolha salva antes da
 * primeira pintura; aqui só se mantém o estado, sincroniza com a preferência do usuário e grava cada troca. */
const CHAVE = "b2bon.theme";
const DURACAO_TRANSICAO_MS = 200;

function temaAplicado(): ThemeMode {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function aplicar(tema: ThemeMode, comTransicao: boolean): void {
  const raiz = document.documentElement;
  if (comTransicao) {
    raiz.classList.add("tema-em-transicao");
    window.setTimeout(() => raiz.classList.remove("tema-em-transicao"), DURACAO_TRANSICAO_MS);
  }
  raiz.setAttribute("data-theme", tema);
  try {
    localStorage.setItem(CHAVE, tema);
  } catch {
    // navegação privada sem storage: o tema vale para a aba e continua salvo no usuário
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { usuario, definirTemaPreferido } = useAuth();
  const [tema, setTema] = useState<ThemeMode>(temaAplicado);
  const sincronizadoPara = useRef<number | null>(null);

  // Ao entrar (ou trocar de usuário): a preferência salva no servidor vale em qualquer aparelho. Se o usuário ainda
  // não escolheu nada no servidor mas já escolheu escuro neste navegador, a escolha local sobe para o servidor.
  useEffect(() => {
    if (!usuario || sincronizadoPara.current === usuario.id) return;
    sincronizadoPara.current = usuario.id;
    const doServidor = usuario.tema_preferido;
    if (doServidor === "light" || doServidor === "dark") {
      if (doServidor !== temaAplicado()) {
        aplicar(doServidor, false);
        setTema(doServidor);
      }
    } else if (temaAplicado() === "dark") {
      definirTemaPreferido("dark").catch(() => undefined);
    }
  }, [usuario, definirTemaPreferido]);

  const alternarTema = useCallback(() => {
    const novo: ThemeMode = temaAplicado() === "dark" ? "light" : "dark";
    aplicar(novo, true);
    setTema(novo);
    if (usuario) definirTemaPreferido(novo).catch(() => undefined); // a troca já valeu na tela; o servidor é melhor esforço
  }, [usuario, definirTemaPreferido]);

  const valor = useMemo(() => ({ tema, alternarTema }), [tema, alternarTema]);
  return <ThemeContext.Provider value={valor}>{children}</ThemeContext.Provider>;
}
