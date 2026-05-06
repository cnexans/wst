import { createSignal, For, onCleanup, Show } from "solid-js";
import { open } from "@tauri-apps/plugin-dialog";
import {
  cancelIngest,
  ingestFiles,
  onIngestFile,
  onIngestLog,
} from "../lib/tauri";
import type { IngestSummary } from "../lib/tauri";

type RowStatus = "pending" | "ingested" | "skipped" | "failed";

interface FileRow {
  filename: string;
  status: RowStatus;
  reason?: string;
  notes?: string[];
}

function basename(p: string): string {
  const parts = p.split(/[\\/]/);
  return parts[parts.length - 1] || p;
}

export default function IngestModal(props: {
  onClose: () => void;
  onComplete?: () => void | Promise<void>;
}) {
  const [running, setRunning] = createSignal(false);
  const [rows, setRows] = createSignal<FileRow[]>([]);
  const [summary, setSummary] = createSignal<IngestSummary | null>(null);
  const [logs, setLogs] = createSignal<string[]>([]);
  const sessionId = "ingest-" + Math.random().toString(36).slice(2);

  let unsubFile: (() => void) | undefined;
  let unsubLog: (() => void) | undefined;

  onCleanup(() => {
    unsubFile?.();
    unsubLog?.();
  });

  async function pickPaths(directory: boolean) {
    const selection = await open({
      multiple: !directory,
      directory,
      title: directory ? "Elegir carpeta" : "Elegir archivos",
    });
    if (!selection) return;
    const paths = Array.isArray(selection) ? selection : [selection as string];
    if (paths.length === 0) return;
    await runIngest(paths);
  }

  async function runIngest(paths: string[]) {
    setRunning(true);
    setSummary(null);
    setLogs([]);
    setRows(paths.map((p) => ({ filename: basename(p), status: "pending" })));

    unsubFile = await onIngestFile((e) => {
      setRows((curr) => {
        const next = [...curr];
        const target = basename(e.filename);
        const idx = next.findIndex(
          (r) => r.filename === e.filename || r.filename === target,
        );
        const updated: FileRow = {
          filename: target,
          status: e.status,
          reason: e.reason,
          notes: e.notes,
        };
        if (idx >= 0) next[idx] = updated;
        else next.push(updated);
        return next;
      });
    });

    unsubLog = await onIngestLog((line) => {
      setLogs((curr) => [...curr, line]);
    });

    try {
      const result = await ingestFiles(paths, {}, sessionId);
      setSummary(result);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setLogs((curr) => [...curr, `Error: ${msg}`]);
    } finally {
      setRunning(false);
      unsubFile?.();
      unsubLog?.();
      unsubFile = undefined;
      unsubLog = undefined;
      try {
        await props.onComplete?.();
      } catch (_e) {
        /* refresh failures are non-fatal */
      }
    }
  }

  async function cancel() {
    try {
      await cancelIngest(sessionId);
    } catch (_e) {
      /* best-effort */
    }
  }

  function close() {
    if (running()) return;
    props.onClose();
  }

  return (
    <div
      class="detail-overlay"
      onClick={(e) => e.target === e.currentTarget && close()}
    >
      <div class="detail-panel ingest-panel">
        <button
          class="detail-close"
          onClick={close}
          title="Cerrar"
          disabled={running()}
        >
          ×
        </button>

        <h2 class="extras-title">Ingestar documentos</h2>
        <p class="extras-subtitle">
          Elegí archivos PDF/EPUB o una carpeta para incorporar a la
          biblioteca.
        </p>

        <Show when={!running() && rows().length === 0}>
          <div class="ingest-pickers">
            <button
              class="extras-btn install"
              onClick={() => pickPaths(false)}
            >
              Elegir archivos
            </button>
            <button
              class="extras-btn install"
              onClick={() => pickPaths(true)}
            >
              Elegir carpeta
            </button>
          </div>
          <p class="ingest-hint">
            Los PDFs escaneados se procesan automáticamente con OCR si las
            herramientas están instaladas; si no, se ingiere el texto y los
            metadatos disponibles y se avisa por archivo.
          </p>
        </Show>

        <Show when={rows().length > 0}>
          <ul class="ingest-list">
            <For each={rows()}>
              {(r) => (
                <li class={`ingest-row ingest-row-${r.status}`}>
                  <span class="ingest-row-name">{r.filename}</span>
                  <span class="ingest-row-status">
                    <Show when={r.status === "pending"}>…</Show>
                    <Show when={r.status === "ingested"}>✓ ingerido</Show>
                    <Show when={r.status === "skipped"}>
                      → {r.reason || "saltado"}
                    </Show>
                    <Show when={r.status === "failed"}>
                      × {r.reason || "falló"}
                    </Show>
                  </span>
                  <Show when={r.notes && r.notes.length > 0}>
                    <ul class="ingest-row-notes">
                      <For each={r.notes!}>{(n) => <li>{n}</li>}</For>
                    </ul>
                  </Show>
                </li>
              )}
            </For>
          </ul>
        </Show>

        <Show when={summary() !== null}>
          <p class="ingest-summary">
            Listo — {summary()!.ingested} ingeridos · {summary()!.skipped}{" "}
            saltados · {summary()!.failed} fallaron
          </p>
        </Show>

        <Show when={logs().length > 0}>
          <details class="ingest-log-details">
            <summary>Detalles ({logs().length} líneas)</summary>
            <pre class="ingest-log">{logs().join("\n")}</pre>
          </details>
        </Show>

        <div class="ingest-footer">
          <Show
            when={running()}
            fallback={
              <button class="extras-btn install" onClick={close}>
                Cerrar
              </button>
            }
          >
            <button class="extras-btn upgrade" onClick={cancel}>
              Cancelar
            </button>
          </Show>
        </div>
      </div>
    </div>
  );
}
