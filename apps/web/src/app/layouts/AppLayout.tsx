import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Menu } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { LeftSidebar } from "./LeftSidebar";

/**
 * App shell, in two shapes.
 *
 * From `md` up it is the fixed 260px sidebar + scrollable content region the
 * 3-column design assumes. Below that the sidebar becomes an off-canvas drawer
 * behind a top bar: a 260px column on a phone leaves nothing for the answer,
 * which is the one thing on screen that matters. The content region is only
 * height-constrained on `md` — on a phone the page scrolls as a whole, so the
 * chat panel is not squeezed into a viewport it has to share with the header.
 */
export function AppLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  // Navigating from the drawer must close it — otherwise the destination
  // renders underneath and the user has to dismiss the menu by hand.
  useEffect(() => setDrawerOpen(false), [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="md:grid md:h-dvh md:grid-cols-[260px_1fr]">
      <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-border bg-card px-3 py-2 md:hidden">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Open the menu"
          aria-expanded={drawerOpen}
          aria-controls="app-sidebar"
          onClick={() => setDrawerOpen(true)}
        >
          <Menu />
        </Button>
        <span className="font-semibold tracking-tight">KnowVeris AI</span>
      </header>

      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          aria-hidden="true"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      <div
        id="app-sidebar"
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-[260px] transition-transform duration-200 md:static md:z-auto md:w-auto md:translate-x-0 md:transition-none",
          drawerOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <LeftSidebar onNavigate={() => setDrawerOpen(false)} />
      </div>

      {/* `scrollbar-gutter: stable` reserves the scrollbar's width whether or not
          it is showing. Without it, the first piece of content that pushes a page
          past the viewport — a fifth row in the dashboard's history card — takes
          ~15px off the content region at the moment it appears, and every column
          under it re-flows. */}
      <main className="min-w-0 scrollbar-gutter-stable md:h-dvh md:overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
