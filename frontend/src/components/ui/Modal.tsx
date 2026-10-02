import { useEffect, useId, useRef, type ReactNode } from "react";

interface ModalProps {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function Modal({ title, open, onClose, children }: ModalProps) {
  const idTitulo = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  // `onClose` costuma ser uma função nova a cada render da tela que usa o modal. Antes ele estava nas dependências do
  // efeito abaixo, que então rodava a cada tecla digitada num campo do modal e devolvia o foco ao contêiner — o campo
  // só aceitava um caractere por vez (bug real 2026-10-02: confirmação de exclusão de tenant). Guardado numa ref, o
  // foco vai para o modal só quando ele ABRE.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    containerRef.current?.focus();

    function aoTeclar(event: KeyboardEvent) {
      if (event.key === "Escape") onCloseRef.current();
    }
    document.addEventListener("keydown", aoTeclar);
    return () => document.removeEventListener("keydown", aoTeclar);
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/60 backdrop-blur-sm sm:items-center"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        tabIndex={-1}
        className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-2xl border border-border2 bg-surf p-6 outline-none sm:rounded-2xl"
      >
        <div className="mb-4 flex items-center justify-between">
          <div id={idTitulo} className="font-head text-base font-bold text-text">
            {title}
          </div>
          <button
            onClick={onClose}
            aria-label="Fechar"
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-surf2 text-muted"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
