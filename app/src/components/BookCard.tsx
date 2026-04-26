import { setSelectedDoc } from "../lib/store";
import type { Document } from "../lib/types";
import CoverImage from "./CoverImage";

interface Props {
  doc: Document;
}

export default function BookCard(props: Props) {
  return (
    <div class="book-card" onClick={() => setSelectedDoc(props.doc)}>
      <CoverImage doc={props.doc} />
      <div class="book-card-info">
        <div class="book-card-title" title={props.doc.title}>
          {props.doc.title}
        </div>
        <div class="book-card-author" title={props.doc.author}>
          {props.doc.author}
        </div>
      </div>
    </div>
  );
}
