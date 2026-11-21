import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { fetchHealth, fetchNotifications, markNotificationsRead } from "../api";
import { when } from "../format";

const links = [
  { to: "/dashboard", label: "Dashboard", end: false },
  { to: "/", label: "Case queue", end: true },
  { to: "/institutions", label: "Institutions", end: false },
  { to: "/runs", label: "Runs", end: false },
  { to: "/docs", label: "How it works", end: false },
  { to: "/audit", label: "Audit log", end: false },
];

const titles: Record<string, string> = {
  "/": "Case queue",
  "/dashboard": "Dashboard",
  "/institutions": "Institutions",
  "/runs": "Batch runs",
  "/docs": "How it works",
  "/audit": "Audit log",
};

export function Shell() {
  const location = useLocation();
  const [syncedAt, setSyncedAt] = useState("");
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [notes, setNotes] = useState<{ id: string; at: string; detail: string; actor: string }[]>(
    [],
  );

  useEffect(() => {
    const base =
      titles[location.pathname] ?? (location.pathname.startsWith("/cases/") ? "Case" : "Forge");
    document.title = `${base} — Forge`;
  }, [location.pathname]);

  useEffect(() => {
    fetchHealth()
      .then((health) => {
        setSyncedAt(health.syncedAt);
      })
      .catch(() => undefined);
  }, []);

  function refreshNotes() {
    fetchNotifications()
      .then((payload) => {
        setUnread(payload.unread);
        setNotes(
          payload.items.map((item) => ({
            id: item.id,
            at: item.at,
            detail: item.detail,
            actor: item.actor,
          })),
        );
      })
      .catch(() => undefined);
  }

  useEffect(() => {
    refreshNotes();
  }, [location.pathname]);

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand">
            <svg className="bolt" viewBox="0 0 24 24" aria-hidden="true">
              <path fill="currentColor" d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" />
            </svg>
            Forge
          </NavLink>
          <div className="top-tools">
            <p className="sync">{syncedAt ? `Books synced ${when(syncedAt)}` : "Syncing books"}</p>
            <button
              type="button"
              className="bell"
              aria-label={unread ? `${unread} unread notifications` : "Notifications"}
              onClick={() => {
                setOpen((value) => !value);
                if (!open) {
                  markNotificationsRead()
                    .then(refreshNotes)
                    .catch(() => undefined);
                }
              }}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  fill="currentColor"
                  d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22zm7-6V11a7 7 0 0 0-5-6.7V4a2 2 0 1 0-4 0v.3A7 7 0 0 0 5 11v5l-2 2v1h18v-1l-2-2z"
                />
              </svg>
              {unread > 0 ? <span className="dot">{unread > 9 ? "9+" : unread}</span> : null}
            </button>
            {open ? (
              <div className="note-panel" role="dialog" aria-label="Notifications">
                {notes.length === 0 ? (
                  <p>No new analyst activity.</p>
                ) : (
                  notes.map((note) => (
                    <p key={note.id}>
                      <strong>{note.actor}</strong> {note.detail}{" "}
                      <span className="meta">{when(note.at)}</span>
                    </p>
                  ))
                )}
              </div>
            ) : null}
            <p className="analyst" title="Signed in">
              <span className="avatar" aria-hidden="true">
                AO
              </span>
              Amira Okonkwo
            </p>
          </div>
        </div>
      </header>
      <nav className="gov-nav" aria-label="Service">
        <ul>
          {links.map((link) => (
            <li key={link.to}>
              <NavLink to={link.to} end={link.end}>
                {({ isActive }) => (
                  <span aria-current={isActive ? "page" : undefined}>{link.label}</span>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main>
        <div className="gov-width">
          <Outlet />
        </div>
      </main>
    </>
  );
}
