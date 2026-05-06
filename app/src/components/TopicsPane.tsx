import { Show, createSignal, onCleanup } from "solid-js";
import {
  buildTopics,
  onTopicsEvent,
  type TopicsEvent,
} from "../lib/tauri";
import { allTopicsVocab, refreshLibraryState } from "../lib/store";

type Phase =
  | "idle"
  | "confirm"
  | "running"
  | "done"
  | "error";

export default function TopicsPane() {
  const [phase, setPhase] = createSignal<Phase>("idle");
  const [error, setError] = createSignal<string | null>(null);
  const [statusLine, setStatusLine] = createSignal<string>("");
  const [progress, setProgress] = createSignal<{ index: number; total: number } | null>(null);
  const [showAdvanced, setShowAdvanced] = createSignal(false);
  const [nTopicsInput, setNTopicsInput] = createSignal("");

  const startBuild = async () => {
    setPhase("running");
    setError(null);
    setStatusLine("Iniciando…");
    setProgress(null);

    const unlisten = await onTopicsEvent((event: TopicsEvent) => {
      switch (event.event) {
        case "phase":
          setStatusLine(phaseLabel(event.name));
          setProgress(null);
          break;
        case "doc":
          setStatusLine(`Asignando ${event.index}/${event.total}…`);
          setProgress({ index: event.index, total: event.total });
          break;
        case "done":
          setStatusLine(
            `Listo: ${event.vocabulary.length} temas, ${event.assigned_count} documentos.`
          );
          break;
      }
    });

    try {
      const parsed = parseInt(nTopicsInput(), 10);
      const opts = Number.isFinite(parsed) && parsed > 0 ? { nTopics: parsed } : {};
      await buildTopics(opts);
      await refreshLibraryState();
      setPhase("done");
    } catch (err) {
      setError(String(err));
      setPhase("error");
    } finally {
      unlisten();
    }
  };

  const reset = () => {
    setPhase("idle");
    setError(null);
    setStatusLine("");
    setProgress(null);
    setNTopicsInput("");
    setShowAdvanced(false);
  };

  onCleanup(() => {
    // any in-flight listener is cleaned in startBuild's finally
  });

  return (
    <div class="topics-pane">
      <div class="sidebar-section-label sidebar-section-sep">
        Temas (Topic modeling)
      </div>
      <div class="topics-pane-body">
        <Show when={allTopicsVocab().length > 0}>
          <p class="topics-pane-hint">
            Vocabulario actual: {allTopicsVocab().length} temas.
          </p>
        </Show>
        <button
          class="btn btn-primary btn-small"
          disabled={phase() === "running"}
          onClick={() => setPhase("confirm")}
        >
          {phase() === "running" ? "Reconstruyendo…" : "Reconstruir vocabulario"}
        </button>
      </div>

      <Show when={phase() === "confirm"}>
        <div class="topics-confirm">
          <p>
            Esto recomputa los temas para toda la biblioteca. Puede tardar unos minutos.
          </p>
          <div class="topics-confirm-advanced">
            <button
              type="button"
              class="topics-link"
              onClick={() => setShowAdvanced(!showAdvanced())}
            >
              {showAdvanced() ? "Ocultar avanzado" : "Mostrar avanzado"}
            </button>
            <Show when={showAdvanced()}>
              <label class="topics-confirm-field">
                <span>Número de temas (vacío = auto-detect)</span>
                <input
                  type="number"
                  min="2"
                  max="50"
                  value={nTopicsInput()}
                  onInput={(e) => setNTopicsInput(e.currentTarget.value)}
                  placeholder="auto"
                />
              </label>
            </Show>
          </div>
          <div class="topics-confirm-actions">
            <button class="btn btn-primary btn-small" onClick={startBuild}>
              Reconstruir
            </button>
            <button class="btn btn-secondary btn-small" onClick={reset}>
              Cancelar
            </button>
          </div>
        </div>
      </Show>

      <Show when={phase() === "running"}>
        <div class="topics-progress">
          <p class="topics-progress-line">{statusLine()}</p>
          <Show when={progress()}>
            <progress
              max={progress()!.total}
              value={progress()!.index}
              class="topics-progress-bar"
            />
          </Show>
        </div>
      </Show>

      <Show when={phase() === "done"}>
        <div class="topics-done">
          <p>{statusLine()}</p>
          <button class="btn btn-secondary btn-small" onClick={reset}>
            Cerrar
          </button>
        </div>
      </Show>

      <Show when={phase() === "error"}>
        <div class="topics-error">
          <p>{error()}</p>
          <button class="btn btn-secondary btn-small" onClick={reset}>
            Cerrar
          </button>
        </div>
      </Show>
    </div>
  );
}

function phaseLabel(name: string): string {
  switch (name) {
    case "backfill_previews":
      return "Generando previews de contenido…";
    case "embedding":
      return "Embeddings y clustering…";
    case "assigning":
      return "Asignando temas…";
    case "saving":
      return "Guardando vocabulario…";
    case "subjects":
      return "Backfill de subjects…";
    default:
      return name;
  }
}
