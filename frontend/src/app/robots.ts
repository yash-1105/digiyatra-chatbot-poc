import type { MetadataRoute } from "next";

/** POC: keep the whole site (and especially /admin) out of search engines. */
export default function robots(): MetadataRoute.Robots {
  return { rules: [{ userAgent: "*", disallow: "/" }] };
}
