"use client";
import { createContext, useContext } from "react";
import type { Locale } from "@/lib/i18n/dictionary";

export const ChatLanguage = createContext<Locale>("en");
const labels = {
  en: {
    title: "Digi Yatra Assistant", approved: "Answers from approved sources", clear: "Clear conversation", close: "Close assistant",
    clearQuestion: "Clear this conversation?", clearButton: "Clear", cancel: "Cancel", conversation: "Conversation",
    welcome: "Namaste! Welcome to Digi Yatra.", greeting: "I can help with registration, boarding passes, the airport journey, privacy and troubleshooting. Please don’t share personal details such as Aadhaar numbers.",
    suggestions: "Suggested questions", input: "Type your question", placeholder: "Ask about Digi Yatra…", send: "Send message",
    hint: "Enter to send · Shift+Enter for a new line", remaining: "characters left", typing: "The assistant is typing…",
    resolved: "Did this resolve your issue?", yes: "Yes", no: "No", thanks: "Thank you for your feedback.",
    unresolved: "Sorry this didn't resolve your issue. You can:", rephrase: "Rephrase your question or ask about one specific step.",
    email: "Email customer care at", device: "with your device model and app version. Never share Aadhaar numbers or OTPs.",
    gate: "For problems at an airport gate, ask the airport staff on site.", support: "Support & Contact information",
    feedbackError: "Couldn't send — please try again.", retry: "Retry", notSent: "Not sent.",
    generated: "AI-generated · verify important details", sources: "Sources", sourceFile: "Source file:", newTab: "opens in a new tab",
    you: "You said:", assistant: "Assistant said:", open: "Open Digi Yatra Assistant", closeLauncher: "Close Digi Yatra Assistant", ask: "Ask Digi Yatra Assistant",
    requestError: "The selected AI provider could not respond. Please try again shortly.",
  },
  hi: {
    title: "डिजी यात्रा सहायक", approved: "स्वीकृत स्रोतों पर आधारित जवाब", clear: "बातचीत मिटाएँ", close: "सहायक बंद करें",
    clearQuestion: "यह बातचीत मिटाएँ?", clearButton: "मिटाएँ", cancel: "रद्द करें", conversation: "बातचीत",
    welcome: "नमस्ते! डिजी यात्रा में आपका स्वागत है।", greeting: "पंजीकरण, बोर्डिंग पास, एयरपोर्ट की प्रक्रिया, गोपनीयता और ऐप की समस्याओं में मदद के लिए पूछें। कृपया आधार नंबर जैसी निजी जानकारी साझा न करें।",
    suggestions: "आप ये सवाल पूछ सकते हैं", input: "अपना सवाल लिखें", placeholder: "डिजी यात्रा के बारे में पूछें…", send: "संदेश भेजें",
    hint: "भेजने के लिए Enter · नई पंक्ति के लिए Shift+Enter", remaining: "अक्षर बाकी", typing: "सहायक जवाब लिख रहा है…",
    resolved: "क्या आपकी समस्या हल हुई?", yes: "हाँ", no: "नहीं", thanks: "आपकी प्रतिक्रिया के लिए धन्यवाद।",
    unresolved: "आपकी समस्या हल नहीं हुई। आप ये कर सकते हैं:", rephrase: "सवाल दूसरे शब्दों में या किसी एक चरण के बारे में पूछें।",
    email: "ग्राहक सहायता को ईमेल करें:", device: "अपने डिवाइस का मॉडल और ऐप का संस्करण बताएँ। आधार नंबर या ओटीपी कभी साझा न करें।",
    gate: "एयरपोर्ट गेट पर समस्या हो तो वहाँ के कर्मचारियों से पूछें।", support: "सहायता और संपर्क जानकारी",
    feedbackError: "प्रतिक्रिया नहीं भेजी जा सकी — फिर प्रयास करें।", retry: "फिर प्रयास करें", notSent: "नहीं भेजा गया।",
    generated: "AI का जवाब · ज़रूरी जानकारी की पुष्टि करें", sources: "स्रोत", sourceFile: "स्रोत फ़ाइल:", newTab: "नए टैब में खुलता है",
    you: "आपका सवाल:", assistant: "सहायक का जवाब:", open: "डिजी यात्रा सहायक खोलें", closeLauncher: "डिजी यात्रा सहायक बंद करें", ask: "डिजी यात्रा सहायक से पूछें",
    requestError: "चुने गए AI प्रदाता से जवाब नहीं मिला। कृपया थोड़ी देर बाद फिर प्रयास करें।",
  },
};
export function useChatText() { return labels[useContext(ChatLanguage)]; }
export const hindiStarters = ["डिजी यात्रा में पंजीकरण कैसे करूँ?", "बोर्डिंग पास की PDF कैसे अपलोड करूँ?", "मेरा डेटा कहाँ संग्रहीत होता है?", "मेरे बोर्डिंग पास का नाम आधार से मेल नहीं खाता"];
