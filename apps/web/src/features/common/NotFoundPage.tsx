import { Link } from "react-router-dom";

import { buttonVariants } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <main className="grid min-h-dvh place-items-center p-8 text-center">
      <div className="space-y-3">
        <h1 className="text-4xl font-bold">404</h1>
        <p className="text-muted-foreground">This page does not exist.</p>
        <Link to="/" className={buttonVariants({ variant: "outline" })}>
          Back to dashboard
        </Link>
      </div>
    </main>
  );
}
