import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export function InstallBanner() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    function handler(event: Event) {
      event.preventDefault();
      setDeferredPrompt(event as BeforeInstallPromptEvent);
    }
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  if (!deferredPrompt || dismissed) return null;

  return (
    <div className="fixed top-0 right-0 left-0 z-[200] flex items-center justify-between gap-2.5 bg-cyan px-4 py-2.5 text-sm font-semibold text-bg">
      <span>📱 Instalar B2B ON na tela inicial?</span>
      <div className="flex gap-2">
        <button
          className="rounded-md bg-bg px-3 py-1 text-xs font-bold text-cyan"
          onClick={async () => {
            await deferredPrompt.prompt();
            await deferredPrompt.userChoice;
            setDeferredPrompt(null);
          }}
        >
          Instalar
        </button>
        <button className="text-lg text-bg" onClick={() => setDismissed(true)}>
          ✕
        </button>
      </div>
    </div>
  );
}
