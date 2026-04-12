export interface Document {
  id: number;
  title: string;
  author: string;
  doc_type: string;
  year: number | null;
  publisher: string | null;
  isbn: string | null;
  language: string | null;
  tags: string[];
  page_count: number | null;
  summary: string | null;
  toc: string | null;
  subject: string | null;
  filename: string;
  original_filename: string;
  file_path: string;
  file_hash: string;
  ingested_at: string;
}

export interface DocTypeCount {
  doc_type: string;
  count: number;
}

export interface LibraryStats {
  total: number;
  by_type: DocTypeCount[];
}

export const DOC_TYPE_LABELS: Record<string, string> = {
  book: "Books",
  novel: "Novels",
  textbook: "Textbooks",
  paper: "Papers",
  "class-notes": "Notes",
  exercises: "Exercises",
  "guide-theory": "Theory Guides",
  "guide-practice": "Practice Guides",
};
