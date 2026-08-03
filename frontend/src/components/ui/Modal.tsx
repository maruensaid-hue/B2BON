import type { ReactNode } from "react";

interface ModalProps {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function Modal({ title, open, onClose, children }: ModalProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-bg/88 backdrop-blur-sm sm:items-center"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-2xl border border-border2 bg-surf p-6 sm:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="font-head text-base font-bold text-text">{title}</div>
          <button
            onClick={onClose}
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
