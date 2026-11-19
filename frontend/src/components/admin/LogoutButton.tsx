"use client";

import { useState } from "react";
import { Loader2, LogOut } from "lucide-react";
import { logoutAdmin } from "@/lib/api/auth-client";

export function LogoutButton() {
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        await logoutAdmin();
        window.location.assign("/admin/login");
      }}
      className="flex items-center gap-1.5 rounded border border-line px-3 py-1.5 text-brand hover:border-brand hover:bg-brand-soft disabled:opacity-60"
    >
      {busy ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <LogOut aria-hidden="true" className="h-4 w-4" />}
      Logout
    </button>
  );
}
