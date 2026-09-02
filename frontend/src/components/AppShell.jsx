import { navigate } from "../core/router";
import { IconArrowLeft, IconCalendar, IconHistory, IconHome } from "./icons";

const NAV_ITEMS = [
  { path: "/", label: "Home", icon: IconHome, match: (segments) => segments.length === 0 },
  { path: "/book", label: "Book", icon: IconCalendar, match: (segments) => segments[0] === "book" },
  {
    path: "/history",
    label: "History",
    icon: IconHistory,
    match: (segments) => segments[0] === "history",
  },
];

export function AppShell({ segments, title, onBack, children }) {
  return (
    <div className="app-shell">
      <header className="app-shell__topbar">
        {onBack ? (
          <button type="button" className="icon-button" onClick={onBack} aria-label="Go back">
            <IconArrowLeft aria-hidden="true" />
          </button>
        ) : (
          <span className="app-shell__brand" aria-hidden="true" />
        )}
        <span className="app-shell__title">{title}</span>
        <span className="app-shell__spacer" aria-hidden="true" />
      </header>

      <main className="app-shell__content">{children}</main>

      <nav className="app-shell__nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => {
          const active = item.match(segments);
          const Icon = item.icon;
          return (
            <button
              key={item.path}
              type="button"
              className={`app-shell__nav-item ${active ? "app-shell__nav-item--active" : ""}`}
              onClick={() => navigate(item.path)}
              aria-current={active ? "page" : undefined}
            >
              <Icon aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
