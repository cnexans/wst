import { createSignal, For, onMount, Show } from "solid-js";
import { getExtrasStatus, installExtra } from "../lib/tauri";
import type { ExtraInfo } from "../lib/tauri";

const EXTRA_LABELS: Record<string, { name: string; icon: string }> = {
  ocr: { name: "OCR", icon: "🔍" },
  topics: { name: "Topic Modeling", icon: "🏷️" },
};

type InstallState = "idle" | "installing" | "done" | "error";

interface ExtraEntry {
  key: string;
  info: ExtraInfo;
}

export default function ExtrasPanel(props: { onClose: () => void }) {
  const [extras, setExtras] = createSignal<ExtraEntry[]>([]);
  const [loading, setLoading] = createSignal(true);
  const [installState, setInstallState] = createSignal<Record<string, InstallState>>({});
  const [installLog, setInstallLog] = createSignal<Record<string, string>>({});

  onMount(async () => {
    await refresh();
  });

  async function refresh() {
    setLoading(true);
    try {
      const status = await getExtrasStatus();
      setExtras(Object.entries(status).map(([key, info]) => ({ key, info })));
    } finally {
      setLoading(false);
    }
  }

  async function handleInstall(key: string, upgrade = false) {
    setInstallState((s) => ({ ...s, [key]: "installing" }));
    setInstallLog((l) => ({ ...l, [key]: "" }));
    try {
      const out = await installExtra(key, upgrade);
      setInstallLog((l) => ({ ...l, [key]: out || "Instalado correctamente." }));
      setInstallState((s) => ({ ...s, [key]: "done" }));
      await refresh();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setInstallLog((l) => ({ ...l, [key]: msg }));
      setInstallState((s) => ({ ...s, [key]: "error" }));
    }
  }

  return (
    <div class="detail-overlay" onClick={(e) => e.target === e.currentTarget && props.onClose()}>
      <div class="detail-panel extras-panel">
        <button class="detail-close" onClick={props.onClose} title="Cerrar">×</button>

        <h2 class="extras-title">Extras instalables</h2>
        <p class="extras-subtitle">
          Funciones opcionales que requieren paquetes adicionales.
        </p>

        <Show when={loading()}>
          <p class="extras-loading">Cargando estado...</p>
        </Show>

        <Show when={!loading()}>
          <For each={extras()}>
            {({ key, info }) => {
              const label = EXTRA_LABELS[key] ?? { name: key, icon: "📦" };
              const state = () => installState()[key] ?? "idle";
              const log = () => installLog()[key] ?? "";

              return (
                <div class={`extras-card ${info.installed ? "installed" : ""}`}>
                  <div class="extras-card-header">
                    <span class="extras-icon">{label.icon}</span>
                    <div class="extras-card-info">
                      <span class="extras-name">{label.name}</span>
                      <span class="extras-desc">{info.description}</span>
                    </div>
                    <div class="extras-status-area">
                      <Show when={info.installed}>
                        <span class="extras-badge installed">✓ Instalado</span>
                        <button
                          class="extras-btn upgrade"
                          disabled={state() === "installing"}
                          onClick={() => handleInstall(key, true)}
                        >
                          {state() === "installing" ? "Actualizando…" : "Actualizar"}
                        </button>
                      </Show>
                      <Show when={!info.installed}>
                        <span class="extras-badge missing">✗ No instalado</span>
                        <button
                          class="extras-btn install"
                          disabled={state() === "installing"}
                          onClick={() => handleInstall(key)}
                        >
                          {state() === "installing" ? "Instalando…" : "Instalar"}
                        </button>
                      </Show>
                    </div>
                  </div>

                  <Show when={log()}>
                    <pre
                      class={`extras-log ${state() === "error" ? "error" : state() === "done" ? "done" : ""}`}
                    >{log()}</pre>
                  </Show>
                </div>
              );
            }}
          </For>
        </Show>
      </div>
    </div>
  );
}
