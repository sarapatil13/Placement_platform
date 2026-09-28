import { ReactNode, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/client";
import type { PaginatedNotifications } from "../api/types";

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

const STUDENT_NAV: NavItem[] = [
  { to: "/app", label: "Drives", end: true },
  { to: "/app/applications", label: "My Applications" },
  { to: "/app/resumes", label: "Resumes" },
  { to: "/app/profile", label: "Profile" },
  { to: "/app/notifications", label: "Notifications" },
];

const ADMIN_NAV: NavItem[] = [
  { to: "/app", label: "Dashboard", end: true },
  { to: "/app/admin/drives", label: "Drives" },
  { to: "/app/admin/applications", label: "Applications" },
  { to: "/app/admin/students", label: "Students" },
  { to: "/app/admin/companies", label: "Companies" },
  { to: "/app/admin/audit", label: "Audit Log" },
];

function useUnreadCount(enabled: boolean): number {
  const [count, setCount] = useState(0);
  const location = useLocation();
  useEffect(() => {
    if (!enabled) return;
    void api
      .get<PaginatedNotifications>("/notifications", { params: { limit: 1, unread_only: true } })
      .then(({ data }) => setCount(data.unread_count))
      .catch(() => undefined);
  }, [enabled, location.pathname]);
  return count;
}

export function Layout() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const unread = useUnreadCount(user?.role === "student");
  const nav = isAdmin ? ADMIN_NAV : STUDENT_NAV;

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark">PP</span>
          <span className="brand-name">Placement Platform</span>
        </div>
        <nav className="sidebar-nav">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `side-link ${isActive ? "active" : ""}`}
            >
              {item.label}
              {item.to === "/app/notifications" && unread > 0 ? (
                <span className="nav-badge">{unread}</span>
              ) : null}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="user-chip">
            <span className="user-name">{user?.full_name}</span>
            <span className="user-role">{user?.role.replace("_", " ")}</span>
          </div>
          <button className="btn btn-ghost btn-block" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <h1>{title}</h1>
      {actions ? <div className="page-head-actions">{actions}</div> : null}
    </header>
  );
}