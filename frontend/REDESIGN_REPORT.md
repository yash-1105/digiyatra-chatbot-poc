# Frontend visual redesign — 19 November 2026

Public URL: https://digiyatra-chatbot-poc.vercel.app  
Frontend implementation commit: `d18c2fc`  
Vercel production deployment: `dpl_41tSpBvmMjDjn9xDsGNTNHj4RAuF` (**READY**)  
Deployment URL: https://digiyatra-chatbot-djz2fbsbm-yash-1105s-projects.vercel.app

## Scope and design

This release changes frontend presentation only. The user's three screenshots and https://digiyatrafoundation.com/ establish the reference: deep purple/navy, white navigation, violet pill actions, large Poppins typography, generous white sections, cyan/teal/blue/magenta hero effects and an asymmetric app-download layout. Hindi uses the existing Noto Sans Devanagari font.

The homepage now has a full-width centered hero with lightweight CSS light trails, an editorial “Driving efficiency in airports” section, registration guidance beside an original wallet illustration, and alternating dark/light information sections. Existing approved content, airport-snapshot qualifications, resource tabs, official store links, FAQs, support links and independent-site disclosure remain. No statistics were copied from the reference screenshots.

Chat, admin login and dashboard share the new colors and typography. Provider/language selection, message formatting, citations, feedback, history, authentication/session checks, metrics, chart/table views and analytics behavior retain their existing implementation. No API endpoints, request/response types, model settings, backend files, knowledge data, database schema or infrastructure were changed. Railway was not redeployed; billing, secrets, resources and credentials were not changed.

## Logo authorization — unresolved

The official SVG was located at https://digiyatrafoundation.com/images/logo/digiyatra-white.svg. Public availability does not establish permission for reuse or redistribution on this independent portal. The owner was asked to confirm permission; confirmation has not been received.

**The release deliberately uses a consistent plain-text identity, not the official logo.** No official logo or photographs were copied or recreated. `public/branding/README.md` records the approval requirement and asset provenance. On confirmed authorization, the original asset can be stored there and used by the shared `LogoMark` component. The phone graphic is clearly labeled “Concept illustration · not an app screen.” The persistent independent-site identification and accurate footer disclaimer remain.

## Changed files

All committed changes are inside `frontend/`.

| Files | Presentation changes |
| --- | --- |
| `src/app/globals.css`, `src/app/layout.tsx` | Purple design tokens, accessible contrast modes, typography, responsive styles, motion and browser surface styling. |
| `src/app/page.tsx` | Existing information-section ordering. |
| `src/components/layout/SiteHeader.tsx`, `SiteFooter.tsx`, `UtilityBar.tsx` | Dark navigation/footer, app-download action, mobile menu presentation, discreet admin link and independent identity. |
| `src/components/brand/LogoMark.tsx`, `public/branding/README.md` | Shared plain-text identity and explicit official-logo approval gate. |
| `src/components/home/HeroSection.tsx`, `AboutSection.tsx`, `RegistrationSection.tsx` | Hero/light trails, editorial information layout, registration/download illustration and localized headings; existing carousel controls/content and links preserved. |
| `src/components/chat/ChatWidget.tsx` | Header, launcher, spacing and responsive window styling. State, API, provider, citation and feedback implementations unchanged. |
| `src/components/admin/AdminHeader.tsx`, `DashboardView.tsx`, `src/app/admin/login/page.tsx` | Branded navigation/login and styled panels/metric cards. Dashboard changes are class names only. |
| `src/components/ui/Section.tsx`, `SectionHeading.tsx`, `Container.tsx`, `Card.tsx` | Shared spacing, heading scale/alignment and surface geometry. |
| `scripts/visual-redesign-e2e.mjs`, `scripts/admin-e2e.mjs` | Presentation regressions and portable installed-Chrome selection/explicit test-context cleanup. |
| `PRODUCT.md`, `DESIGN.md`, `REDESIGN_REPORT.md` | Frontend scope, visual direction, authorization status and release evidence. |

## Build and regression results

- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm run build`: passed locally and on Vercel; all eight pages generated. No new dependencies added.
- Presentation regression: **80/80 checks passed** at desktop 1440×1000, laptop 1366×768, tablet 820×1180 and mobile 390×844. Covered existing section anchors, official download links, airport/FAQ search, mobile navigation/Escape, chat bounds, language/provider persistence, high contrast, reduced motion, enlarged text, public login form and anonymous admin protection.
- Existing admin end-to-end script: **28/28 checks passed** on a fresh synthetic database, then **27/27** on populated synthetic data (the fresh-empty-state check was correctly skipped). Covered incorrect/correct sign-in, HttpOnly/SameSite cookies, navigation, citations, follow-ups, Yes/No feedback, counter changes, duplicate/unknown feedback rejection, filters, chart/table toggle, tablet/mobile layouts and logout/session protection.
- Existing chat end-to-end script: passed registration/follow-up questions, source details, same-origin API calls and conversation restart.
- The local interaction tests used the existing backend with a mocked model transport and a throwaway SQLite database under the ignored project cache. These validate UI integration, not model answer quality. No production analytics or admin accounts were modified.
- The design detector reported no mechanical findings. Screenshots were reviewed against the reference; the admin identity contrast issue found in the first pass was fixed.

## Production verification

**43/43 live Chrome checks passed** on the actual production alias, at desktop and mobile sizes. No response fixtures were substituted.

- New deep-purple homepage and independent identity displayed, without an authentication popup or page overflow.
- Official app links and footer disclaimer remained. The redesigned About/Registration headings switched with the existing site Hindi selector.
- Chat defaults remained English/Sarvam. Two real `sarvam-105b` answers (one English, one Hindi) rendered with valid source citations, expandable source metadata and both feedback buttons. The chat remained inside the viewport.
- Switching to Anthropic and reloading preserved the selection and conversation history. This presentation test did not claim successful Anthropic inference or change existing provider/account settings.
- The existing public admin login form and new styling loaded. Anonymous `/admin/dashboard` redirected to login; the analytics API returned 401. No real production administrator session was created.
- No browser runtime errors occurred.

Synthetic live questions used the backend's **already existing** operator-signed evaluation mode, traversing the real Vercel proxy and Railway chat endpoint with real inference while disabling test-event persistence. No backend code or configuration was changed to perform this verification; no production analytics were written. Full Yes/No feedback submissions were verified in the isolated acceptance instance rather than against production data.

The production alias points to Vercel deployment `dpl_41tSpBvmMjDjn9xDsGNTNHj4RAuF`, built from frontend implementation `d18c2fc`.

## Screenshots

Generated screenshots are local artifacts and intentionally ignored by Git:

- `screenshots/redesign/desktop-home.png`, `mobile-home.png`: homepage.
- `screenshots/redesign/desktop-about.png`, `desktop-registration.png`: reference-inspired editorial/download sections.
- `screenshots/redesign/desktop-full.png`, `mobile-full.png`: complete information content.
- `screenshots/redesign/desktop-chat.png`, `mobile-chat.png`: provider/language controls, including Hindi.
- `screenshots/redesign/desktop-login.png`, `mobile-login.png`: login/validation.
- `screenshots/admin-dashboard-desktop.png`, `admin-dashboard-tablet.png`, `admin-dashboard-mobile.png`: authenticated synthetic dashboard.
- `screenshots/redesign/live-desktop-home.png`, `live-mobile-home.png`, `live-desktop-chat.png`, `live-mobile-chat.png`, `live-desktop-login.png`, `live-mobile-login.png`: actual deployed frontend.

## Limits

The official logo and reference photographs remain excluded until appropriate authorization is supplied. Full production admin sign-in was not exercised with a real administrator credential; complete sign-in/dashboard/logout behavior was verified in the isolated instance, with live anonymous access guards checked separately. Existing provider/account availability and knowledge approval restrictions are unchanged by this visual release.
