/**
 * DEVELOPMENT MOCK DATA — canned answers for the chatbot UI while the
 * FastAPI + Sarvam AI + LanceDB backend is not yet built.
 *
 * These are hand-written summaries of `knowledge/raw/` documents matched by
 * simple keywords. They are NOT AI output and the UI labels them as mock.
 */
import type { ChatSource } from "@/lib/api/types";
import { officialLinks } from "@/lib/config";

export interface MockAnswer {
  keywords: readonly string[];
  answer: string;
  sources: readonly ChatSource[];
}

const kb = (file: string, snippet?: string): ChatSource => ({ title: `Knowledge base: ${file}`, snippet });

export const mockAnswers: readonly MockAnswer[] = [
  {
    keywords: ["register", "registration", "enrol", "enroll", "sign up", "signup", "create account", "digilocker"],
    answer:
      "To register on Digi Yatra:\n1. Download the official Digi Yatra app and register with your mobile number linked to Aadhaar, then validate with OTP.\n2. Link your identity through DigiLocker, or directly with Aadhaar if you are not on DigiLocker.\n3. Take a clear selfie — it is validated against your Aadhaar photo.\n4. Upload your boarding pass. The name must exactly match your identity proof.",
    sources: [kb("registration_details.md", "Use your mobile number linked to Aadhaar. Validate with OTP."), { title: "Enrolment using DigiLocker (video)", url: "https://www.youtube.com/watch?v=7z7iLNSkFg4" }],
  },
  {
    keywords: ["airport", "airports", "available at", "which city", "supported"],
    answer:
      "The project knowledge base lists 24 airports where Digi Yatra is available, including Delhi (DEL), Mumbai (BOM), Bengaluru (BLR), Hyderabad (HYD), Chennai (MAA) and Kolkata (CCU). Airport availability changes over time, so please confirm on the official list of current airports before you travel.",
    sources: [kb("available_airports.md"), { title: "Official list of current Digi Yatra airports", url: officialLinks.currentAirports }],
  },
  {
    keywords: ["privacy", "data", "stored", "store", "safe", "secure", "biometric", "delete my data"],
    answer:
      "Digi Yatra follows privacy by design. Your identity credentials, travel documents and face biometrics are stored only in a secure wallet on your own phone — there is no central database. When you choose to share credentials with the departure airport, they are shared in encrypted form and purged from the airport's systems within 24 hours of the flight's departure.",
    sources: [kb("general_03_data_privacy_security.md", "No centralized storage of Personally Identifiable Information (PII)."), kb("airport_data_sharing.md")],
  },
  {
    keywords: ["delete", "uninstall", "remove account", "deactivate", "opt out", "opt-out"],
    answer:
      "To remove your Digi Yatra data, delete the credential in the app or simply uninstall the app. Because Digi Yatra keeps no centralised user profiles, this removes your data from the ecosystem — there is no need to send a deletion request.",
    sources: [kb("delete_digiyatra.md"), kb("contact_us.md")],
  },
  {
    keywords: ["name mismatch", "mismatch", "name on", "boarding pass upload", "upload fail", "initial"],
    answer:
      "The name on your boarding pass must exactly match the name on your Aadhaar. If there is a mismatch — including initials, single names or a different name order — please contact your airline to update the name on your booking. Also check that the boarding pass has a clear, valid QR code and try the 'Scan Boarding Pass' option.",
    sources: [kb("support_02_registration_profile.md"), kb("support_01_app_troubleshooting.md")],
  },
  {
    keywords: ["child", "minor", "infant", "kid", "family", "dependent", "wife", "husband", "spouse"],
    answer:
      "Minors can be added under a registered adult's account: choose 'Add Credentials' → 'Add minor Credentials' and follow the steps (adult consent and Aadhaar verification are required). Each adult passenger, including a spouse on the same PNR, must register separately on their own smartphone. Infants or children under 5 without Aadhaar should use the normal manual process.",
    sources: [kb("general_04_app_eligibility.md"), kb("support_05_usage_eligibility.md"), kb("support_02_registration_profile.md")],
  },
  {
    keywords: ["international", "foreign", "passport", "abroad"],
    answer:
      "Digi Yatra is currently available only for domestic flights departing from supported airports in India, and enrolment currently requires Aadhaar.",
    sources: [kb("support_04_general_information.md"), kb("general_04_app_eligibility.md")],
  },
  {
    keywords: ["otp", "forbidden", "error", "crash", "not working", "selfie", "vpn", "device lock"],
    answer:
      "Common fixes:\n• 'Forbidden' error — disable any VPN, set date & time to automatic, clear the app cache and retry.\n• OTP not received — this may be a temporary delay from the network provider or UIDAI; try again later.\n• Selfie errors — use good lighting and a plain background, and remove glasses or face coverings.\n• App freezing — update to the latest version and restart your device.\nIf the issue continues, email customercare@digiyatrafoundation.com with your device model, OS version and app version.",
    sources: [kb("support_01_app_troubleshooting.md")],
  },
  {
    keywords: ["how does", "how it works", "work", "process", "gate", "e-gate", "journey", "boarding"],
    answer:
      "At the airport: (1) at the departure entry gate, scan your boarding pass on the Digi Yatra e-gate and look into the camera; (2) at the pre-security e-gate, look into the camera and proceed after validation; (3) at the boarding gate, look into the biometric camera and proceed to the aircraft. Remember to share your credentials with the departure airport in advance — typically from 24 hours up to 60 minutes before departure.",
    sources: [kb("airport_guide.md"), kb("general_02_how_it_works.md")],
  },
  {
    keywords: ["mandatory", "compulsory", "voluntary", "forced"],
    answer:
      "No. Digi Yatra is purely voluntary, and enrolment must always be with your full consent. Regular manual identity verification and boarding processes remain available.",
    sources: [kb("general_01_introduction.md"), kb("support_03_airport_availability.md")],
  },
  {
    keywords: ["contact", "support", "help", "email", "customer care", "complaint"],
    answer:
      "You can reach Digi Yatra customer care at customercare@digiyatrafoundation.com. Please do not share Aadhaar numbers or copies — they are not needed. For failures at the airport, contact the airport team first, or write in with your flight number, PNR and travel date within 24 hours of departure.",
    sources: [kb("contact_us.md"), { title: "Digi Yatra Foundation — Contact us", url: officialLinks.contact }],
  },
];

export const mockFallback: MockAnswer = {
  keywords: [],
  answer:
    "I don't have a prepared mock answer for that question yet. In this development build the assistant only returns a small set of canned answers; the AI-powered assistant (FastAPI + Sarvam AI + knowledge-base search) will be connected in the next milestone. Try one of the suggested questions, or browse the FAQ section on this page.",
  sources: [],
};
