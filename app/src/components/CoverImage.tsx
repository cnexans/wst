import { createEffect, createSignal } from "solid-js";
import { convertFileSrc } from "@tauri-apps/api/core";
import { covers, setCover } from "../lib/store";
import { ensureCover } from "../lib/tauri";
import type { Document } from "../lib/types";

interface Props {
  doc: Document;
}

export default function CoverImage(props: Props) {
  const [loading, setLoading] = createSignal(true);
  const [error, setError] = createSignal(false);

  const coverUrl = () => {
    const path = covers()[props.doc.id];
    return path ? convertFileSrc(path) : null;
  };

  createEffect(() => {
    const doc = props.doc;
    const cached = covers()[doc.id];
    if (cached !== undefined) return;

    ensureCover(doc.id, doc.isbn, doc.file_path).then((path) => {
      if (path) {
        setCover(doc.id, path);
      } else {
        setCover(doc.id, "");
      }
    });
  });

  return (
    <div class="cover-container">
      {coverUrl() ? (
        <img
          src={coverUrl()!}
          alt={props.doc.title}
          class={`cover-image ${loading() ? "loading" : ""}`}
          onLoad={() => setLoading(false)}
          onError={() => {
            setLoading(false);
            setError(true);
          }}
        />
      ) : null}
      {(!coverUrl() || error()) && (
        <div class="cover-placeholder">
          <div class="cover-placeholder-text">
            {props.doc.title.slice(0, 40)}
          </div>
        </div>
      )}
    </div>
  );
}
