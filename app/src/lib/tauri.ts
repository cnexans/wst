import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { Document, LibraryStats } from "./types";

export async function listDocuments(
  docType?: string,
  sortBy?: string,
  topic?: string,
  subject?: string
): Promise<Document[]> {
  return invoke("list_documents", {
    docType: docType ?? null,
    sortBy: sortBy ?? null,
    topic: topic ?? null,
    subject: subject ?? null,
  });
}

export async function searchDocuments(
  query: string,
  docType?: string,
  topic?: string,
  subject?: string
): Promise<Document[]> {
  return invoke("search_documents", {
    query,
    docType: docType ?? null,
    topic: topic ?? null,
    subject: subject ?? null,
  });
}

export async function getSubjects(): Promise<string[]> {
  return invoke("get_subjects");
}

export async function getDocument(id: number): Promise<Document | null> {
  return invoke("get_document", { id });
}

export async function getLibraryStats(): Promise<LibraryStats> {
  return invoke("get_library_stats");
}

export async function getTopicsVocabulary(): Promise<string[]> {
  return invoke("get_topics_vocabulary");
}

export async function getCover(id: number): Promise<string | null> {
  return invoke("get_cover", { id });
}

export async function openPdf(filePath: string): Promise<void> {
  return invoke("open_pdf", { filePath });
}

export async function revealInFinder(filePath: string): Promise<void> {
  return invoke("reveal_in_finder", { filePath });
}

export async function editDocument(
  id: number,
  fields: Record<string, string>
): Promise<Document> {
  const args = ["edit", String(id), "--format", "json", "-y"];
  for (const [key, value] of Object.entries(fields)) {
    args.push("--set", `${key}=${value}`);
  }
  const raw = await invoke<string>("run_wst_command", { args });
  const result = JSON.parse(raw);
  return result.data.entry;
}

export async function backupToIcloud(): Promise<string> {
  return invoke("backup_to_icloud");
}

export type BackupProvider = "icloud" | "gdrive" | "s3";

export interface BackupProviderInfo {
  name: BackupProvider;
  configured: boolean;
}

export async function backupDocument(id: number, provider: BackupProvider): Promise<void> {
  await invoke<string>("run_wst_command", {
    args: ["backup", provider, String(id), "--format", "json"],
  });
}

/** @deprecated use backupDocument(id, "icloud") */
export async function backupDocumentToIcloud(id: number): Promise<void> {
  return backupDocument(id, "icloud");
}

export interface BackupAllResult {
  provider: BackupProvider;
  backed_up_files: number;
}

export async function backupAll(provider: BackupProvider): Promise<BackupAllResult> {
  const raw = await invoke<string>("run_wst_command", {
    args: ["backup", provider, "--all", "--format", "json"],
  });
  const result = JSON.parse(raw);
  return result.data as BackupAllResult;
}

export async function listBackupProviders(): Promise<BackupProviderInfo[]> {
  const raw = await invoke<string>("run_wst_command", {
    args: ["backup", "providers", "--format", "json"],
  });
  const result = JSON.parse(raw);
  return result.data.providers as BackupProviderInfo[];
}

export async function configureBackupProvider(
  provider: "icloud" | "gdrive",
  opts: { subfolder?: string; path?: string }
): Promise<{ root: string }> {
  const args = ["backup", provider, "--configure"];
  if (opts.subfolder) args.push("--subfolder", opts.subfolder);
  if (provider === "gdrive" && opts.path) args.push("--path", opts.path);
  args.push("--format", "json");
  const raw = await invoke<string>("run_wst_command", { args });
  const result = JSON.parse(raw);
  return { root: result.data.root };
}

export interface ExtraInfo {
  installed: boolean;
  description: string;
  package: string;
  check_modules: string[];
  system_deps: string[];
}

export async function getExtrasStatus(): Promise<Record<string, ExtraInfo>> {
  const raw = await invoke<string>("run_wst_command", {
    args: ["install", "--list", "--json"],
  });
  return JSON.parse(raw);
}

export async function installExtra(name: string, upgrade = false): Promise<string> {
  const args = ["install", name];
  if (upgrade) args.push("--upgrade");
  return invoke<string>("run_wst_command", { args });
}

// ---------------------------------------------------------------------------
// RFC 0013 — ingest from GUI
// ---------------------------------------------------------------------------

export interface IngestFileEvent {
  event: "file";
  filename: string;
  status: "ingested" | "skipped" | "failed";
  reason: string;
  dest_path: string;
  notes: string[];
}

export interface IngestSummary {
  processed: number;
  ingested: number;
  skipped: number;
  failed: number;
  cleaned_inbox_removed: number;
}

export interface IngestOpts {
  force_ocr?: boolean;
}

export async function ingestFiles(
  paths: string[],
  opts: IngestOpts,
  sessionId: string
): Promise<IngestSummary> {
  return invoke("ingest_files", { paths, opts, sessionId });
}

export async function cancelIngest(sessionId: string): Promise<void> {
  return invoke("cancel_ingest", { sessionId });
}

export function onIngestFile(cb: (e: IngestFileEvent) => void) {
  return listen<IngestFileEvent>("ingest:file", (event) => cb(event.payload));
}

export function onIngestLog(cb: (line: string) => void) {
  return listen<string>("ingest:log", (event) => cb(event.payload));
}

// ---------------------------------------------------------------------------
// RFC 0016 — OCR and topics from GUI
// ---------------------------------------------------------------------------

export interface OcrResult {
  ok_count: number;
  skipped_count: number;
  failed_count: number;
}

export async function ocrDocument(
  id: number,
  opts: { force?: boolean; language?: string } = {}
): Promise<OcrResult> {
  const args = ["ocr", String(id), "--format", "json"];
  if (opts.force) args.push("--force");
  if (opts.language) args.push("--language", opts.language);
  const raw = await invoke<string>("run_wst_command", { args });
  const result = JSON.parse(raw);
  return result.data as OcrResult;
}

export type TopicsEvent =
  | { event: "phase"; name: string; vocabulary?: string[] }
  | { event: "doc"; index: number; total: number; id: number; topics: string[] }
  | {
      event: "done";
      vocabulary: string[];
      assigned_count: number;
      subjects_updated: number;
    };

export interface TopicsBuildResult {
  vocabulary: string[];
  assigned_count: number;
  subjects_updated: number;
}

export async function buildTopics(
  opts: { nTopics?: number } = {}
): Promise<TopicsBuildResult> {
  return invoke("build_topics", {
    opts: { n_topics: opts.nTopics ?? null },
  });
}

export function onTopicsEvent(cb: (e: TopicsEvent) => void) {
  return listen<TopicsEvent>("topics:event", (event) => cb(event.payload));
}

export function onTopicsLog(cb: (line: string) => void) {
  return listen<string>("topics:log", (event) => cb(event.payload));
}
