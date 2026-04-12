import { For } from "solid-js";
import { documents } from "../lib/store";
import BookCard from "./BookCard";

export default function BookGrid() {
  return (
    <div class="book-grid">
      <For each={documents()}>{(doc) => <BookCard doc={doc} />}</For>
      {documents().length === 0 && (
        <div class="empty-state">No documents found.</div>
      )}
    </div>
  );
}
