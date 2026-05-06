import { For, Show, createSignal, onMount } from "solid-js";
import {
  backupAll,
  configureBackupProvider,
  listBackupProviders,
  type BackupProvider,
  type BackupProviderInfo,
} from "../lib/tauri";

const PROVIDER_LABELS: Record<BackupProvider, string> = {
  icloud: "iCloud",
  gdrive: "Google Drive",
  s3: "S3",
};

export default function BackupPane() {
  const [providers, setProviders] = createSignal<BackupProviderInfo[]>([]);
  const [busy, setBusy] = createSignal<BackupProvider | null>(null);
  const [status, setStatus] = createSignal<string | null>(null);
  const [error, setError] = createSignal(false);
  const [wizardFor, setWizardFor] = createSignal<BackupProvider | null>(null);
  const [wizardSubfolder, setWizardSubfolder] = createSignal("wst");
  const [wizardPath, setWizardPath] = createSignal("");
  const [wizardError, setWizardError] = createSignal<string | null>(null);

  const refresh = async () => {
    try {
      setProviders(await listBackupProviders());
    } catch {
      setProviders([]);
    }
  };

  onMount(refresh);

  const flashStatus = (msg: string, isError = false) => {
    setError(isError);
    setStatus(msg);
    setTimeout(() => setStatus(null), 4000);
  };

  const handleBackupAll = async (p: BackupProvider) => {
    setBusy(p);
    try {
      const result = await backupAll(p);
      flashStatus(`${PROVIDER_LABELS[p]}: ${result.backed_up_files} archivos respaldados ✓`);
    } catch (err) {
      flashStatus(String(err), true);
    } finally {
      setBusy(null);
    }
  };

  const openWizard = (p: BackupProvider) => {
    setWizardFor(p);
    setWizardSubfolder("wst");
    setWizardPath("");
    setWizardError(null);
  };

  const submitWizard = async () => {
    const p = wizardFor();
    if (!p || p === "s3") return;
    setWizardError(null);
    try {
      await configureBackupProvider(p, {
        subfolder: wizardSubfolder() || "wst",
        path: wizardPath() || undefined,
      });
      setWizardFor(null);
      await refresh();
      flashStatus(`${PROVIDER_LABELS[p]} configurado ✓`);
    } catch (err) {
      setWizardError(String(err));
    }
  };

  return (
    <div class="backup-pane">
      <div class="sidebar-section-label sidebar-section-sep">Backup</div>
      <ul class="sidebar-list">
        <For each={providers()}>
          {(p) => (
            <li class="backup-provider-row">
              <div class="backup-provider-row-head">
                <span>{PROVIDER_LABELS[p.name]}</span>
                <span
                  class={
                    p.configured
                      ? "backup-provider-status backup-provider-status--ok"
                      : "backup-provider-status backup-provider-status--off"
                  }
                >
                  {p.configured ? "✓" : "○"}
                </span>
              </div>
              <div class="backup-provider-actions">
                <Show
                  when={p.configured}
                  fallback={
                    p.name === "s3" ? (
                      <span class="backup-provider-hint">
                        Configurar en CLI: <code>wst backup s3 --configure</code>
                      </span>
                    ) : (
                      <button
                        class="btn btn-secondary btn-small"
                        onClick={() => openWizard(p.name)}
                      >
                        Configurar
                      </button>
                    )
                  }
                >
                  <button
                    class="btn btn-primary btn-small"
                    disabled={busy() !== null}
                    onClick={() => handleBackupAll(p.name)}
                  >
                    {busy() === p.name ? "Respaldando…" : "Respaldar todo"}
                  </button>
                </Show>
              </div>
            </li>
          )}
        </For>
      </ul>

      <Show when={status()}>
        <p
          class={`backup-pane-status${error() ? " backup-pane-status--error" : ""}`}
        >
          {status()}
        </p>
      </Show>

      <Show when={wizardFor()}>
        {(p) => (
          <div class="backup-wizard">
            <h4 class="backup-wizard-title">
              Configurar {PROVIDER_LABELS[p()]}
            </h4>
            <Show when={p() === "gdrive"}>
              <label class="backup-wizard-field">
                <span>Ruta a Google Drive (opcional)</span>
                <input
                  type="text"
                  placeholder="(auto-detect)"
                  value={wizardPath()}
                  onInput={(e) => setWizardPath(e.currentTarget.value)}
                />
              </label>
            </Show>
            <label class="backup-wizard-field">
              <span>Subcarpeta</span>
              <input
                type="text"
                value={wizardSubfolder()}
                onInput={(e) => setWizardSubfolder(e.currentTarget.value)}
              />
            </label>
            <Show when={wizardError()}>
              <p class="backup-pane-status backup-pane-status--error">
                {wizardError()}
              </p>
            </Show>
            <div class="backup-wizard-actions">
              <button class="btn btn-primary btn-small" onClick={submitWizard}>
                Guardar
              </button>
              <button
                class="btn btn-secondary btn-small"
                onClick={() => setWizardFor(null)}
              >
                Cancelar
              </button>
            </div>
          </div>
        )}
      </Show>
    </div>
  );
}
