import type { ReactNode } from "react";
import { ChatWidget } from "@/components/chat/ChatWidget";
import { LanguageNotice } from "./LanguageNotice";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";
import { UtilityBar } from "./UtilityBar";

export function PublicShell({ children, withChat = true }: { children: ReactNode; withChat?: boolean }) {
  return (
    <>
      <UtilityBar />
      <SiteHeader />
      <LanguageNotice />
      <main id="main-content" tabIndex={-1} className="focus:outline-none">
        {children}
      </main>
      <SiteFooter />
      {withChat ? <ChatWidget /> : null}
    </>
  );
}
