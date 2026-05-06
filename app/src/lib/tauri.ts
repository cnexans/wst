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

export async function backupDocumentToIcloud(id: number): Promise<void> {
  await invoke<string>("run_wst_command", {
    args: ["backup", "icloud", String(id), "--format", "json"],
  });
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
