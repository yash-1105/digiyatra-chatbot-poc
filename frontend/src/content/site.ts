/**
 * Curated homepage content.
 *
 * Every statement below is taken from documents in `knowledge/raw/`
 * (file names noted per block). Deliberately EXCLUDED:
 *  - the DY-IPT international passenger trial (draft document, not current fact),
 *  - the India AI Summit 2026 event FAQ (historical, event-specific),
 *  - download / journey / usage statistics (point-in-time, may be outdated),
 *  - anything not present in the source documents (no invented announcements,
 *    contact numbers or airport availability).
 */
import { officialLinks } from "@/lib/config";

export interface SourceRef {
  file: string;
}

/* ------------------------------------------------------------------ */
/* Hero carousel + highlights                                          */
/* ------------------------------------------------------------------ */

export type SlideArt = "face" | "phone" | "shield";

export interface HeroSlide {
  id: string;
  title: string;
  caption: string;
  art: SlideArt;
  href: string;
  cta: string;
}

export const heroSlides: HeroSlide[] = [
  {
    id: "paperless",
    title: "Paperless, contactless airport entry",
    caption: "Digi Yatra uses facial verification to validate identity and travel details at airport entry, security and boarding gates.",
    art: "face",
    href: "#journey",
    cta: "See the airport journey",
  },
  {
    id: "enrol",
    title: "One-time enrolment on the Digi Yatra app",
    caption: "Register with your mobile number, link your identity through DigiLocker or Aadhaar, and validate with a selfie.",
    art: "phone",
    href: "#registration",
    cta: "Read the registration guide",
  },
  {
    id: "privacy",
    title: "Privacy by design",
    caption: "Your credentials stay in a secure wallet on your own phone. There is no central storage of personal data.",
    art: "shield",
    href: "#privacy",
    cta: "How your data is protected",
  },
];

export interface Highlight {
  text: string;
  href: string;
}

// Sources: general_01_introduction.md, general_02_how_it_works.md,
// general_03_data_privacy_security.md, support_04_general_information.md, linkedin_privacy_security.md
export const highlights: Highlight[] = [
  { text: "Using Digi Yatra is purely voluntary — regular manual processes remain available", href: "#about" },
  { text: "Share your credentials with the departure airport 24 hours to 60 minutes before departure", href: "#how-it-works" },
  { text: "Biometric data is purged from airport systems within 24 hours of flight departure", href: "#privacy" },
  { text: "Digi Yatra is currently available only for domestic flights from supported airports", href: "#airports" },
  { text: "Onboarding is only possible through the official app — there is no email-based onboarding", href: "#privacy" },
  { text: "Name on the boarding pass must exactly match the name on Aadhaar", href: "#registration" },
];

/* ------------------------------------------------------------------ */
/* Welcome + mission panels                                            */
/* ------------------------------------------------------------------ */

// Sources: general_01_introduction.md, about_us.md
export const welcome = {
  intro:
    "Digi Yatra is a decentralised digital wallet system for air travel in India, led by the Ministry of Civil Aviation. It aims to provide a seamless, paperless and hassle-free journey for passengers by using a single token of face biometrics to digitally validate identity and travel data.",
  operator:
    "It is operated by the Digi Yatra Foundation, a not-for-profit company established under Section 8 of the Companies Act, 2013.",
  panels: [
    {
      key: "mission" as const,
      body: "To redefine the travel experience by seamlessly blending innovation, technology, and safety.",
    },
    {
      key: "vision" as const,
      body: "To make every journey a hassle-free and secure experience, so passengers feel at ease from check-in to boarding.",
    },
    {
      key: "commitment" as const,
      body: "Privacy by design and consent first — personal data remains under the passenger's control on their own device.",
    },
  ],
};

/* ------------------------------------------------------------------ */
/* What's New tabs                                                     */
/* ------------------------------------------------------------------ */

export interface Announcement {
  title: string;
  date: string; // ISO date
  href?: string;
}

/**
 * Announcements are a dynamically maintained list that will be managed from
 * the admin dashboard. No approved announcements exist yet, so the UI shows
 * an empty state. Do NOT add items here unless they are officially approved.
 */
export const announcements: Announcement[] = [];

export interface ResourceItem {
  title: string;
  meta: string;
  /** Omitted for references that have no verified public URL. */
  href?: string;
}

// Source: general_01_introduction.md
export const guidelines: ResourceItem[] = [
  {
    title: "Digi Yatra Guidelines — Aeronautical Information Circular (AIC) No. 09/2022 issued by the Directorate General of Civil Aviation (DGCA)",
    meta: "Dated 18 April 2022 | Reference cited in the Digi Yatra knowledge base",
  },
  {
    title: "Digi Yatra Foundation Privacy Policy",
    meta: "External link | digiyatrafoundation.com",
    href: officialLinks.privacyPolicy,
  },
];

// Sources: general_07_video_resources.md, share_data_with_app.md
export const videoTutorials: ResourceItem[] = [
  { title: "Enrolment using Aadhaar", meta: "Video | YouTube", href: "https://www.youtube.com/watch?v=y6xTGrpfAGs" },
  { title: "Enrolment using DigiLocker", meta: "Video | YouTube", href: "https://www.youtube.com/watch?v=7z7iLNSkFg4" },
  { title: "Enrolment in 3 simple steps", meta: "Video | YouTube", href: "https://www.youtube.com/watch?v=-nlJBCwg0nM" },
  { title: "How to add a dependent / minor", meta: "Video | YouTube", href: "https://www.youtube.com/watch?v=j2lw7LljME0" },
  { title: "Sharing your boarding pass PDF with the app", meta: "Video | YouTube", href: "https://www.youtube.com/watch?v=jdb1Ph-QH9g" },
  { title: "Understanding data safety (Self-Sovereign Identity)", meta: "Video | YouTube", href: "https://www.youtube.com/watch?v=Wlc6iqgwQDU" },
];

// Source: registration_details.md
export const appDownloads: ResourceItem[] = [
  { title: "Digi Yatra for Android — Google Play Store", meta: "Official app listing | play.google.com", href: officialLinks.playStore },
  { title: "Digi Yatra for iPhone — Apple App Store", meta: "Official app listing | apps.apple.com", href: officialLinks.appStore },
];

/* ------------------------------------------------------------------ */
/* About                                                               */
/* ------------------------------------------------------------------ */

// Sources: general_01_introduction.md, general_02_how_it_works.md, privacy_policy.csv
export const aboutFacts = [
  {
    title: "What is Digi Yatra?",
    body: "A decentralised, mobile-based identity platform for air travel in India that uses facial biometrics to validate identity and travel details at airport checkpoints.",
  },
  {
    title: "Who operates it?",
    body: "The Digi Yatra Foundation (DYF), a not-for-profit Section 8 company, implements the Digi Yatra Central Ecosystem (DYCE) pursuant to the Digi Yatra Policy issued by the Ministry of Civil Aviation.",
  },
  {
    title: "Is it mandatory?",
    body: "No. Using Digi Yatra is purely voluntary, and data is collected only with the passenger's consent. Regular manual processes are always available.",
  },
  {
    title: "Underlying technology",
    body: "Built on W3C standards using Self-Sovereign Identity (SSI), Verifiable Credentials (VC) and Decentralised Identifiers (DIDs), with a distributed ledger as a decentralised layer of trust.",
  },
];

// Sources: general_01_introduction.md, linkedin_service_information.md
export const benefits = [
  { title: "Faster processing", body: "Reduces the time spent at airport entry, security and boarding gates." },
  { title: "Reduced queues", body: "Minimises waiting times at airport touchpoints." },
  { title: "Seamless and contactless", body: "No need to repeatedly show physical ID or boarding pass at multiple points." },
  { title: "Hygienic", body: "Minimises physical contact and exchange of documents." },
];

/* ------------------------------------------------------------------ */
/* How it works                                                        */
/* ------------------------------------------------------------------ */

// Sources: general_02_how_it_works.md, end_to_end_process.md
export const howItWorks = [
  {
    step: 1,
    title: "One-time enrolment",
    points: [
      "Download the official Digi Yatra app from the Google Play Store or Apple App Store.",
      "Register with your mobile number and OTP.",
      "Link your identity using DigiLocker (preferred) or Aadhaar, and take a selfie for validation.",
      "Your verified credential is stored in the wallet inside the app on your phone.",
    ],
  },
  {
    step: 2,
    title: "Before you travel",
    points: [
      "Scan or upload your bar-coded boarding pass in the app.",
      "Share your credentials with the departure airport — typically from 24 hours up to 60 minutes before scheduled departure.",
      "If your seat or flight details change, re-upload the updated boarding pass.",
    ],
  },
  {
    step: 3,
    title: "At the airport",
    points: [
      "Scan your boarding pass at the Digi Yatra e-gate and look into the camera.",
      "A 1:1 facial match against the credentials you shared validates your identity and travel details.",
      "The same facial verification is used at entry, security and boarding gates.",
    ],
  },
];

export const howItWorksNotes = [
  "After using Digi Yatra e-gates, passengers still follow normal security screening procedures.",
  "If the Digi Yatra system is down, regular manual identity verification and boarding processes are always available.",
  "Digi Yatra works at the departure airport; processing at transit/transfer airports depends on each airport's implementation.",
];

/* ------------------------------------------------------------------ */
/* Registration                                                        */
/* ------------------------------------------------------------------ */

// Sources: registration_details.md, support_02_registration_profile.md, general_04_app_eligibility.md, allowed_passengers.md
export const registrationSteps = [
  { title: "Register on the app", detail: "Use your mobile number linked to Aadhaar and validate it with the OTP." },
  { title: "Link identity credentials", detail: "Link through DigiLocker. If you are not on DigiLocker, register directly with Aadhaar." },
  { title: "Capture your selfie", detail: "Ensure a clear, unobstructed photo in good light with a plain background. It is validated against your Aadhaar photo." },
  { title: "Upload your boarding pass", detail: "Scan it, or share the image/PDF to the app. The name must exactly match your identity proof." },
];

export const registrationTips = [
  { title: "Aadhaar is required", body: "Currently, Aadhaar is mandatory for verification and creating your Digi Yatra ID." },
  { title: "One adult per account", body: "Each adult passenger must register separately on their own smartphone, even on the same PNR." },
  { title: "Travelling with minors", body: "From your own account, choose 'Add Credentials' → 'Add minor Credentials'. Adult consent is required, and Aadhaar verification also applies to minors." },
  { title: "Changed your phone?", body: "Install the app on the new device and repeat the one-time enrolment. Data is stored only on the device." },
  { title: "Carry your ID", body: "It is still recommended to carry your physical Government ID for any exigencies." },
  { title: "App language", body: "The Digi Yatra app currently supports English only." },
];

/* ------------------------------------------------------------------ */
/* Airport journey                                                     */
/* ------------------------------------------------------------------ */

// Source: airport_guide.md
export const journeySteps = [
  {
    title: "Departure entry gate",
    points: ["Scan your boarding pass on the Digi Yatra e-gate", "Look into the camera and get your face scanned", "The e-gate opens to let you into the terminal"],
  },
  {
    title: "Pre-security e-gate",
    points: ["Walk up to the Digi Yatra e-gate at security check", "Look into the camera on the e-gate", "After validation the gate opens; proceed for security screening"],
  },
  {
    title: "Boarding gate",
    points: ["Once your flight starts boarding", "Look into the biometric camera at the boarding gate", "After validation, proceed towards the aircraft"],
  },
];

export const journeyNotes = [
  "The technology at each touchpoint (face-only or boarding-pass scan) depends on the infrastructure deployed by each airport.",
  "Some airlines or security protocols may still ask for a boarding pass at certain checkpoints.",
];

/* ------------------------------------------------------------------ */
/* Supported airports                                                  */
/* ------------------------------------------------------------------ */

export interface Airport {
  code: string;
  name: string;
}

/**
 * Snapshot from `knowledge/raw/available_airports.md`. Airport availability
 * changes over time and this list has NOT been verified as current; the UI
 * labels it as a knowledge-base snapshot and links to the official list.
 * When the admin dashboard exists, this should be served from the backend.
 */
export const airportsSnapshot: { listed: Airport[]; planned: Airport[] } = {
  listed: [
    { code: "VNS", name: "Lal Bahadur Shastri International Airport" },
    { code: "MAA", name: "Chennai International Airport" },
    { code: "BBI", name: "Biju Patnaik International Airport" },
    { code: "VGA", name: "Vijayawada Airport" },
    { code: "VTZ", name: "Visakhapatnam International Airport" },
    { code: "CJB", name: "Coimbatore International Airport" },
    { code: "CCU", name: "Netaji Subhash Chandra Bose International Airport" },
    { code: "IXB", name: "Bagdogra International Airport" },
    { code: "PNQ", name: "Pune International Airport" },
    { code: "PAT", name: "Jay Prakash Narayan Airport" },
    { code: "IDR", name: "Devi Ahilya Bai Holkar Airport" },
    { code: "IXR", name: "Birsa Munda Airport" },
    { code: "GOI", name: "Dabolim Airport" },
    { code: "RPR", name: "Swami Vivekananda Airport" },
    { code: "BOM", name: "Chhatrapati Shivaji Maharaj International Airport" },
    { code: "GAU", name: "Lokpriya Gopinath Bordoloi International Airport" },
    { code: "AMD", name: "Ahmedabad International Airport" },
    { code: "LKO", name: "Chaudhary Charan Singh International Airport" },
    { code: "JAI", name: "Jaipur International Airport" },
    { code: "DEL", name: "Indira Gandhi International Airport" },
    { code: "HYD", name: "Rajiv Gandhi International Airport" },
    { code: "GOX", name: "Manohar International Airport (MOPA)" },
    { code: "COK", name: "Cochin International Airport" },
    { code: "BLR", name: "Kempegowda International Airport" },
  ],
  planned: [
    { code: "IXC", name: "Chandigarh Airport" },
    { code: "SXR", name: "Srinagar International Airport" },
    { code: "IXE", name: "Mangaluru International Airport" },
    { code: "TRV", name: "Thiruvananthapuram International Airport" },
  ],
};

/* ------------------------------------------------------------------ */
/* Privacy & security                                                  */
/* ------------------------------------------------------------------ */

// Sources: general_03_data_privacy_security.md, linkedin_privacy_security.md,
// airport_data_sharing.md, contact_us.md, privacy_policy.csv
export const privacyPrinciples = [
  { title: "Privacy by design", body: "The Digi Yatra Central Ecosystem has no centralised storage of Personally Identifiable Information (PII)." },
  { title: "Data stays on your phone", body: "Identity, travel documents and face biometrics are stored only in a secure wallet within the app on your own smartphone." },
  { title: "Consent first", body: "Credentials are shared, in encrypted form, only with the departure airport and only when you choose to share them." },
  { title: "24-hour purge", body: "Data shared with the airport is purged from its systems within 24 hours of the flight's departure." },
  { title: "No travel-history tracking", body: "Digi Yatra does not track or store travel history centrally. Trip history lives only on your device." },
  { title: "Independent audits", body: "Processes are audited and certified by CERT-In empanelled agencies for privacy and security standards." },
];

export const privacyRights = [
  "Modify or delete your credentials and boarding passes from within the app.",
  "Withdraw consent by deleting the credential or uninstalling the app — no deletion request is needed, since no data is held centrally.",
  "Raise data-privacy grievances by email (see Support & Contact).",
];

export const securityAlert =
  "Onboarding is ONLY possible through the official Digi Yatra mobile app. There is no email-based onboarding — never enter your details on suspicious portals, and never share your Aadhaar number or copies with anyone claiming to provide support.";

/* ------------------------------------------------------------------ */
/* FAQ                                                                 */
/* ------------------------------------------------------------------ */

export interface FaqItem {
  q: string;
  a: string;
}

export interface FaqCategory {
  id: string;
  label: string;
  items: FaqItem[];
}

// Sources: general_*.md, support_0*.md, delete_digiyatra.md, allowed_passengers.md, share_data_with_app.md, available_languages.md
export const faqCategories: FaqCategory[] = [
  {
    id: "general",
    label: "General",
    items: [
      { q: "What is Digi Yatra?", a: "Digi Yatra is a decentralised digital wallet system for air travel in India, led by the Ministry of Civil Aviation. It uses face biometrics to digitally validate identity and travel details for a seamless, paperless journey." },
      { q: "Is Digi Yatra mandatory?", a: "No. Using Digi Yatra is purely voluntary for air passengers, and data is collected only with their consent. Enrolment must always be with your full consent." },
      { q: "Can I use Digi Yatra for international flights?", a: "No. Digi Yatra is currently available only for domestic flights departing from supported airports in India." },
      { q: "Can foreign citizens use Digi Yatra?", a: "Currently the system supports passengers with Aadhaar. Support for other identity documents is on the future roadmap." },
      { q: "Is the app available in regional languages?", a: "Not yet. The Digi Yatra app currently supports English only." },
    ],
  },
  {
    id: "registration",
    label: "Registration",
    items: [
      { q: "Can I register without an Aadhaar card?", a: "Currently, Aadhaar is mandatory for verification and creating your Digi Yatra ID." },
      { q: "My name on Aadhaar and my boarding pass don't match. What should I do?", a: "The name on your boarding pass must exactly match the name on your Aadhaar. If there is a mismatch (including single names, initials or a different name order), contact your airline to update the name on your booking." },
      { q: "How do I add my child?", a: "First create your own adult account. On the home screen choose 'Add Credentials' → 'Add minor Credentials' and follow the steps. Adult consent and Aadhaar verification are required. For infants or children under 5 without Aadhaar, use the normal manual process." },
      { q: "My spouse and I are on the same PNR. Can I add them to my app?", a: "No. Digi Yatra supports one adult passenger per account. Each adult must register separately on their own smartphone." },
      { q: "How do I update my photo?", a: "For security reasons the photo cannot be edited directly. Delete your existing credentials and re-register with a new selfie. This erases past trip history from the device." },
    ],
  },
  {
    id: "travel",
    label: "At the Airport",
    items: [
      { q: "When should I share my credentials with the airport?", a: "Share your credentials with the departure airport in advance — typically from 24 hours up to 60 minutes before the scheduled departure time." },
      { q: "How do I share a boarding pass PDF?", a: "Open the PDF in your phone's files or gallery, tap Share, choose Digi Yatra and grant consent. The details are then shared with the airport." },
      { q: "My seat changed after I uploaded the boarding pass.", a: "Re-upload the updated boarding pass in the app so that the QR code matches the latest airline records." },
      { q: "Why was I asked for my boarding pass after using Digi Yatra?", a: "Some airlines or security protocols may still require a physical or digital boarding pass at certain checkpoints." },
      { q: "What if the Digi Yatra system is down?", a: "Regular manual identity verification and boarding processes are always available as an alternative." },
    ],
  },
  {
    id: "privacy",
    label: "Privacy & Data",
    items: [
      { q: "Where is my data stored?", a: "All personal data and credentials are stored only in a secure wallet on your own smartphone. There is no central repository or database." },
      { q: "How long does the airport keep my data?", a: "Data shared with the departure airport is purged from its systems within 24 hours of the flight's departure." },
      { q: "How do I delete my Digi Yatra account?", a: "Delete the credential in the app or uninstall the app. Because there are no centralised user profiles, this removes your data from the Digi Yatra ecosystem — no deletion request is needed." },
      { q: "Why is my trip history missing?", a: "Trip history is stored only on your device. If the app is reinstalled or its data is cleared, past trips cannot be recovered. This is part of the privacy-by-design approach." },
    ],
  },
  {
    id: "troubleshooting",
    label: "Troubleshooting",
    items: [
      { q: "I'm seeing a 'Forbidden' error when logging in.", a: "This typically happens when accessing the app from outside India, using a VPN, or due to network restrictions. Disable any VPN, set your device date and time to automatic, clear the app cache and try again." },
      { q: "I'm not receiving the OTP.", a: "This may be a temporary delay from the network provider or UIDAI. Try again after some time; if it continues, check with your network provider or UIDAI support." },
      { q: "My boarding pass upload is failing.", a: "Make sure the name exactly matches your Aadhaar and the boarding pass has a clear, valid QR code. Try the 'Scan Boarding Pass' option." },
      { q: "The selfie capture shows an error.", a: "Use a well-lit area with a plain background, remove glasses or face coverings and hold the camera steady." },
      { q: "The app asks me to register again after reinstalling.", a: "Data is stored only on your device. If the app is uninstalled or reinstalled, the local data is lost and you need to re-register." },
      { q: "I'm stuck on the 'Enable Device Lock' screen.", a: "The app uses your phone's screen lock (PIN, pattern, fingerprint or face lock). Make sure a screen lock is active in your phone settings, then clear the app cache and restart the app." },
    ],
  },
];

/* ------------------------------------------------------------------ */
/* Support & contact                                                   */
/* ------------------------------------------------------------------ */

// Sources: contact_us.md, general_05_troubleshooting_support.md, privacy_policy.csv
export const contactChannels = [
  { label: "Customer care", value: "customercare@digiyatrafoundation.com", note: "App and registration issues. Include device model, OS version and app version." },
  { label: "Data privacy grievances", value: "dataprivacy@DigiYatraFoundation.com", note: "Questions about your personal data rights and controls." },
  { label: "Media queries", value: "Media@DigiYatraFoundation.com", note: "For press and media enquiries only." },
];

export const supportGuidance = [
  "Do NOT share Aadhaar numbers or Aadhaar copies — they are not needed to resolve issues.",
  "For most issues, only your name (as saved in the app) and, for tricky cases, your boarding-pass QR/bar code are needed.",
  "For failures at the airport, contact the airport team first. If you write to Digi Yatra, include flight number, PNR and date of travel within 24 hours of departure — airport data is deleted after 24 hours.",
];
