import { announcements } from "@/content/site";
import { EmptyState } from "@/components/ui/EmptyState";
import { ExternalLink } from "@/components/ui/ExternalLink";
import { officialLinks } from "@/lib/config";

function formatDate(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/**
 * Admin-managed announcements. There are no approved announcements yet,
 * so this renders an empty state rather than invented news.
 */
export function AnnouncementsList({ compact = false }: { compact?: boolean }) {
  if (announcements.length === 0) {
    return (
      <EmptyState
        className={compact ? "py-6" : undefined}
        title="No announcements at this time"
        description={
          <>
            Approved announcements will appear here once they are published through the admin dashboard. For the latest
            official updates, visit the{" "}
            <ExternalLink href={officialLinks.news}>Digi Yatra Foundation news page</ExternalLink>.
          </>
        }
      />
    );
  }

  return (
    <ul className="divide-y divide-line">
      {announcements.map((a) => (
        <li key={`${a.date}-${a.title}`} className="py-4">
          {a.href ? (
            <a href={a.href} className="text-brand hover:underline">
              {a.title}
            </a>
          ) : (
            <p className="text-heading">{a.title}</p>
          )}
          <p className="mt-1 text-sm text-ink-soft">{formatDate(a.date)}</p>
        </li>
      ))}
    </ul>
  );
}
