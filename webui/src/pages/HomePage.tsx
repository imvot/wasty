import type { PageId } from "../api/types";

interface Props {
  pages: { id: PageId; title: string; blurb: string }[];
  onOpen: (id: PageId) => void;
}

export default function HomePage({ pages, onOpen }: Props) {
  return (
    <div className="home">
      <header className="home-header">
        <h1>Wasty</h1>
        <p>Pick a page</p>
      </header>
      <nav className="page-list">
        {pages.map((p) => (
          <button
            key={p.id}
            type="button"
            className="page-card"
            onClick={() => onOpen(p.id)}
          >
            <span className="page-card-title">{p.title}</span>
            <span className="page-card-blurb">{p.blurb}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
