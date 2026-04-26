import { onMount } from "solid-js";
import { searchQuery, setSearchQuery } from "../lib/store";

export default function SearchBar() {
  let inputRef!: HTMLInputElement;

  onMount(() => {
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.focus();
      }
    });
  });

  return (
    <div class="search-bar">
      <svg class="search-icon" viewBox="0 0 20 20" fill="currentColor">
        <path
          fill-rule="evenodd"
          d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z"
          clip-rule="evenodd"
        />
      </svg>
      <input
        ref={inputRef}
        type="text"
        placeholder="Search by title, author, tags...  (Cmd+K)"
        value={searchQuery()}
        onInput={(e) => setSearchQuery(e.currentTarget.value)}
        class="search-input"
      />
      {searchQuery() && (
        <button class="search-clear" onClick={() => setSearchQuery("")}>
          &times;
        </button>
      )}
    </div>
  );
}
