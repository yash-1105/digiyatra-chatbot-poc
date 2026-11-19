import Link from "next/link";
import { PublicShell } from "@/components/layout/PublicShell";
import { Container } from "@/components/ui/Container";

export default function NotFound() {
  return (
    <PublicShell>
      <Container className="py-24 text-center">
        <p className="text-sm font-semibold uppercase tracking-wider text-accent">Error 404</p>
        <h1 className="mt-2 text-3xl text-heading">Page not found</h1>
        <p className="mx-auto mt-3 max-w-md text-ink-muted">The page you are looking for does not exist or has been moved.</p>
        <Link href="/" className="btn-pill mt-8 inline-flex rounded-full px-10 py-3 font-medium">
          Go to homepage
        </Link>
      </Container>
    </PublicShell>
  );
}
