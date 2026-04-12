import { Show, For } from "solid-js";
import { selectedDoc, setSelectedDoc, covers } from "../lib/store";
import { openPdf, revealInFinder } from "../lib/tauri";
import { convertFileSrc } from "@tauri-apps/api/core";
import { DOC_TYPE_LABELS } from "../lib/types";

export default function BookDetail() {
  const doc = () => selectedDoc();

  const coverUrl = () => {
    const d = doc();
    if (!d) return null;
    const path = covers()[d.id];
    return path ? convertFileSrc(path) : null;
  };

  const close = () => setSelectedDoc(null);

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") close();
  };

  return (
    <Show when={doc()}>
      {(d) => (
        <div class="detail-overlay" onClick={close} onKeyDown={handleKeyDown}>
          <div class="detail-panel" onClick={(e) => e.stopPropagation()}>
            <button class="detail-close" onClick={close}>
              &times;
            </button>

            <div class="detail-header">
              <div class="detail-cover">
                {coverUrl() ? (
                  <img src={coverUrl()!} alt={d().title} />
                ) : (
                  <div class="cover-placeholder large">
                    <div class="cover-placeholder-text">{d().title}</div>
                  </div>
                )}
              </div>
              <div class="detail-title-area">
                <h2>{d().title}</h2>
                <p class="detail-author">{d().author}</p>
                <div class="detail-actions">
                  <button
                    class="btn btn-primary"
                    onClick={() => openPdf(d().file_path)}
                  >
                    Open PDF
                  </button>
                  <button
                    class="btn btn-secondary"
                    onClick={() => revealInFinder(d().file_path)}
                  >
                    Reveal in Finder
                  </button>
                </div>
              </div>
            </div>

            <div class="detail-meta">
              <MetaRow label="Type" value={DOC_TYPE_LABELS[d().doc_type] ?? d().doc_type} />
              <MetaRow label="Year" value={d().year?.toString()} />
              <MetaRow label="Publisher" value={d().publisher} />
              <MetaRow label="ISBN" value={d().isbn} />
              <MetaRow label="Language" value={d().language} />
              <MetaRow label="Pages" value={d().page_count?.toString()} />
              <MetaRow label="Subject" value={d().subject} />

              <Show when={d().tags.length > 0}>
                <div class="meta-row">
                  <span class="meta-label">Tags</span>
                  <div class="meta-tags">
                    <For each={d().tags}>
                      {(tag) => <span class="tag">{tag}</span>}
                    </For>
                  </div>
                </div>
              </Show>

              <Show when={d().summary}>
                <div class="meta-row meta-row-full">
                  <span class="meta-label">Summary</span>
                  <p class="meta-value">{d().summary}</p>
                </div>
              </Show>

              <Show when={d().toc}>
                <div class="meta-row meta-row-full">
                  <span class="meta-label">Table of Contents</span>
                  <pre class="meta-toc">{d().toc}</pre>
                </div>
              </Show>
            </div>
          </div>
        </div>
      )}
    </Show>
  );
}

function MetaRow(props: { label: string; value?: string | null }) {
  return (
    <Show when={props.value}>
      <div class="meta-row">
        <span class="meta-label">{props.label}</span>
        <span class="meta-value">{props.value}</span>
      </div>
    </Show>
  );
}
