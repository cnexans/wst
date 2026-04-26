import { For } from "solid-js";
import { documents, setSelectedDoc } from "../lib/store";

export default function BookList() {
  return (
    <div class="book-list">
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Author</th>
            <th>Type</th>
            <th>Year</th>
            <th>Subject</th>
          </tr>
        </thead>
        <tbody>
          <For each={documents()}>
            {(doc) => (
              <tr onClick={() => setSelectedDoc(doc)} class="book-list-row">
                <td class="book-list-title">{doc.title}</td>
                <td>{doc.author}</td>
                <td>{doc.doc_type}</td>
                <td>{doc.year ?? "--"}</td>
                <td>{doc.subject ?? "--"}</td>
              </tr>
            )}
          </For>
        </tbody>
      </table>
      {documents().length === 0 && (
        <div class="empty-state">No documents found.</div>
      )}
    </div>
  );
}
