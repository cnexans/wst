import { Show, For, createSignal, createEffect } from "solid-js";
import { selectedDoc, setSelectedDoc, setDocuments, documents } from "../lib/store";
import { openPdf, revealInFinder, getCover, editDocument, getTopicsVocabulary, backupDocumentToIcloud } from "../lib/tauri";
import { DOC_TYPE_LABELS } from "../lib/types";
import type { Document } from "../lib/types";

export default function BookDetail() {
  const doc = () => selectedDoc();
  const [coverUrl, setCoverUrl] = createSignal<string | null>(null);
  const [editing, setEditing] = createSignal(false);
  const [saving, setSaving] = createSignal(false);
  const [saveError, setSaveError] = createSignal<string | null>(null);
  const [backupStatus, setBackupStatus] = createSignal<string | null>(null);
  const [backupError, setBackupError] = createSignal(false);

  // Edit form fields
  const [editTitle, setEditTitle] = createSignal("");
  const [editAuthor, setEditAuthor] = createSignal("");
  const [editDocType, setEditDocType] = createSignal("");
  const [editYear, setEditYear] = createSignal("");
  const [editTags, setEditTags] = createSignal("");
  const [editTopics, setEditTopics] = createSignal<string[]>([]);
  const [vocabulary, setVocabulary] = createSignal<string[]>([]);

  createEffect(async () => {
    const d = doc();
    if (d) {
      const filename = await getCover(d.id);
      setCoverUrl(filename ? `covers://localhost/${filename}` : null);
    } else {
      setCoverUrl(null);
    }
  });

  const openEditPanel = async () => {
    const d = doc();
    if (!d) return;
    setEditTitle(d.title);
    setEditAuthor(d.author);
    setEditDocType(d.doc_type);
    setEditYear(d.year?.toString() ?? "");
    setEditTags(d.tags.join(", "));
    setEditTopics(d.topics ?? []);
    setSaveError(null);
    setEditing(true);
    try {
      const vocab = await getTopicsVocabulary();
      setVocabulary(vocab);
    } catch {
      setVocabulary([]);
    }
  };

  const cancelEdit = () => {
    setEditing(false);
    setSaveError(null);
  };

  const handleSave = async () => {
    const d = doc();
    if (!d) return;

    const fields: Record<string, string> = {};
    if (editTitle() !== d.title) fields["title"] = editTitle();
    if (editAuthor() !== d.author) fields["author"] = editAuthor();
    if (editDocType() !== d.doc_type) fields["doc_type"] = editDocType();
    if (editYear() !== (d.year?.toString() ?? "")) fields["year"] = editYear();

    const currentTags = d.tags.join(", ");
    if (editTags() !== currentTags) fields["tags"] = editTags();
    const topicsStr = editTopics().join(", ");
    const originalTopicsStr = (d.topics ?? []).join(", ");
    if (topicsStr !== originalTopicsStr) fields["topics"] = topicsStr;

    if (Object.keys(fields).length === 0) {
      setEditing(false);
      return;
    }

    setSaving(true);
    setSaveError(null);
    try {
      const updated: Document = await editDocument(d.id, fields);
      // Update the selected doc and the documents list
      setSelectedDoc(updated);
      setDocuments(documents().map((doc) => (doc.id === updated.id ? updated : doc)));
      setEditing(false);
    } catch (err) {
      setSaveError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleBackup = async (id: number) => {
    try {
      await backupDocumentToIcloud(id);
      setBackupError(false);
      setBackupStatus("Guardado en iCloud ✓");
    } catch (err) {
      setBackupError(true);
      setBackupStatus(String(err));
    } finally {
      setTimeout(() => setBackupStatus(null), 3000);
    }
  };

  const close = () => {
    setEditing(false);
    setSelectedDoc(null);
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      if (editing()) cancelEdit();
      else close();
    }
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
                    Abrir PDF
                  </button>
                  <button
                    class="btn btn-secondary"
                    onClick={() => revealInFinder(d().file_path)}
                  >
                    Mostrar en Finder
                  </button>
                  <button
                    class="btn btn-secondary"
                    onClick={() => handleBackup(d().id)}
                    title="Backup a iCloud"
                  >
                    ☁ iCloud
                  </button>
                  <button
                    class="btn btn-secondary"
                    onClick={openEditPanel}
                  >
                    Editar
                  </button>
                </div>
                <Show when={backupStatus()}>
                  <p class={`detail-backup-status${backupError() ? " detail-backup-status--error" : ""}`}>
                    {backupStatus()}
                  </p>
                </Show>
              </div>
            </div>

            <Show when={!editing()}>
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

                <Show when={(d().topics ?? []).length > 0}>
                  <div class="meta-row">
                    <span class="meta-label">Topics</span>
                    <div class="meta-tags">
                      <For each={d().topics}>
                        {(topic) => <span class="tag tag--topic">{topic}</span>}
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
            </Show>

            <Show when={editing()}>
              <div class="edit-form">
                <div class="edit-field">
                  <label class="edit-label">Title</label>
                  <input
                    class="edit-input"
                    type="text"
                    value={editTitle()}
                    onInput={(e) => setEditTitle(e.currentTarget.value)}
                  />
                </div>

                <div class="edit-field">
                  <label class="edit-label">Author</label>
                  <input
                    class="edit-input"
                    type="text"
                    value={editAuthor()}
                    onInput={(e) => setEditAuthor(e.currentTarget.value)}
                  />
                </div>

                <div class="edit-field">
                  <label class="edit-label">Type</label>
                  <select
                    class="edit-input edit-select"
                    value={editDocType()}
                    onChange={(e) => setEditDocType(e.currentTarget.value)}
                  >
                    <For each={Object.entries(DOC_TYPE_LABELS)}>
                      {([value, label]) => (
                        <option value={value}>{label}</option>
                      )}
                    </For>
                  </select>
                </div>

                <div class="edit-field">
                  <label class="edit-label">Year</label>
                  <input
                    class="edit-input"
                    type="text"
                    value={editYear()}
                    onInput={(e) => setEditYear(e.currentTarget.value)}
                    placeholder="e.g. 2024"
                  />
                </div>

                <div class="edit-field">
                  <label class="edit-label">Tags</label>
                  <input
                    class="edit-input"
                    type="text"
                    value={editTags()}
                    onInput={(e) => setEditTags(e.currentTarget.value)}
                    placeholder="comma-separated, e.g. math, logic"
                  />
                </div>

                <div class="edit-field">
                  <label class="edit-label">Topics</label>
                  <Show
                    when={vocabulary().length > 0}
                    fallback={
                      <p class="edit-hint">No topic vocabulary found. Run <code>wst topics build</code> first.</p>
                    }
                  >
                    <div class="edit-topics-list">
                      <For each={vocabulary()}>
                        {(topic) => (
                          <label class="edit-topic-item">
                            <input
                              type="checkbox"
                              checked={editTopics().includes(topic)}
                              onChange={(e) => {
                                if (e.currentTarget.checked) {
                                  setEditTopics([...editTopics(), topic]);
                                } else {
                                  setEditTopics(editTopics().filter((t) => t !== topic));
                                }
                              }}
                            />
                            <span>{topic}</span>
                          </label>
                        )}
                      </For>
                    </div>
                  </Show>
                </div>

                <Show when={saveError()}>
                  <p class="edit-error">{saveError()}</p>
                </Show>

                <div class="edit-actions">
                  <button
                    class="btn btn-primary"
                    onClick={handleSave}
                    disabled={saving()}
                  >
                    {saving() ? "Saving..." : "Save"}
                  </button>
                  <button class="btn btn-secondary" onClick={cancelEdit}>
                    Cancel
                  </button>
                </div>
              </div>
            </Show>
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
