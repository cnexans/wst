import { createSignal, onMount, onCleanup } from "solid-js";
import { getCover } from "../lib/tauri";
import type { Document } from "../lib/types";

interface Props {
  doc: Document;
}

export default function CoverImage(props: Props) {
  let containerRef!: HTMLDivElement;
  const [src, setSrc] = createSignal<string | null>(null);
  const [loaded, setLoaded] = createSignal(false);

  onMount(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          observer.disconnect();
          loadCover();
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(containerRef);
    onCleanup(() => observer.disconnect());
  });

  async function loadCover() {
    const filename = await getCover(props.doc.id);
    if (filename) {
      setSrc(`covers://localhost/${filename}`);
    }
  }

  return (
    <div class="cover-container" ref={containerRef}>
      {src() ? (
        <img
          src={src()!}
          alt={props.doc.title}
          class={`cover-image ${loaded() ? "" : "loading"}`}
          onLoad={() => setLoaded(true)}
          onError={() => setSrc(null)}
          loading="lazy"
        />
      ) : (
        <div class="cover-placeholder">
          <div class="cover-placeholder-text">
            {props.doc.title.slice(0, 60)}
          </div>
        </div>
      )}
    </div>
  );
}
