import { NavLink } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { FileText, History, LayoutDashboard, LogOut, Moon, Sun, Users, X } from "lucide-react";

import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { isAdmin, roleFromUser } from "@/features/auth/roles";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

type NavItem = { to: string; label: string; icon: typeof LayoutDashboard; end?: boolean };
type NavProps = NavItem & { onNavigate?: () => void };

const employeeNav: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/history", label: "History", icon: History },
];

const adminNav: NavItem[] = [
  { to: "/admin/documents", label: "Documents", icon: FileText },
  { to: "/admin/users", label: "Users", icon: Users },
];

/**
 * `onNavigate` is what the mobile drawer passes in: on a phone this component
 * is an overlay, so following a link has to dismiss it. On `md` and up nothing
 * is passed and the sidebar is a plain static column.
 */
export function LeftSidebar({ onNavigate }: { onNavigate?: () => void } = {}) {
  const auth = useAuth();
  const { theme, toggle } = useTheme();
  const profile = auth.user?.profile;
  const name =
    (profile?.name as string | undefined) ??
    profile?.preferred_username ??
    profile?.email ??
    "employee";
  const email = profile?.email ?? "";
  const role = roleFromUser(auth.user) ?? "employee";

  return (
    <aside className="flex h-full flex-col border-r border-border bg-card md:h-dvh">
      <div className="flex items-center justify-between gap-2 px-5 py-4">
        <span className="text-lg font-semibold tracking-tight">KnowVeris AI</span>
        {onNavigate && (
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Close the menu"
            onClick={onNavigate}
          >
            <X />
          </Button>
        )}
      </div>

      <div className="flex items-center gap-3 px-5 py-3">
        <Avatar name={name} />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{name}</p>
          {email && <p className="truncate text-xs text-muted-foreground">{email}</p>}
        </div>
      </div>
      <div className="px-5 pb-3">
        <Badge variant={role === "admin" ? "default" : "secondary"}>{role}</Badge>
      </div>

      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto px-3 py-2">
        {employeeNav.map((item) => (
          <SidebarLink key={item.to} {...item} onNavigate={onNavigate} />
        ))}
        {isAdmin(auth.user) && (
          <>
            <p className="px-3 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Admin
            </p>
            {adminNav.map((item) => (
              <SidebarLink key={item.to} {...item} onNavigate={onNavigate} />
            ))}
          </>
        )}
      </nav>

      <div className="flex items-center justify-between gap-2 border-t border-border p-3">
        <Button variant="ghost" size="sm" onClick={toggle} aria-label="Toggle theme">
          {theme === "dark" ? <Sun /> : <Moon />}
          <span>{theme === "dark" ? "Light" : "Dark"}</span>
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void auth.signoutRedirect()}
        >
          <LogOut />
          <span>Log out</span>
        </Button>
      </div>
    </aside>
  );
}

function SidebarLink({ to, label, icon: Icon, end, onNavigate }: NavProps) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        )
      }
    >
      <Icon className="size-4" />
      {label}
    </NavLink>
  );
}
