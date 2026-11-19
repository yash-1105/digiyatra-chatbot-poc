"""Static safety/UI fallbacks. Generative answers use the selected provider, not translation calls."""

from __future__ import annotations


def fallback(status: str, english: str) -> str:
    if status == "greeting":
        return "नमस्ते! मैं डिजी यात्रा सहायक हूँ। पंजीकरण, बोर्डिंग पास, एयरपोर्ट की प्रक्रिया, गोपनीयता या ऐप की समस्या के बारे में पूछें।"
    if status == "refused":
        return "मैं डिजी यात्रा से जुड़े सवालों में मदद कर सकता हूँ। आंतरिक निर्देश, पासवर्ड, एपीआई कुंजियाँ या अनधिकृत जानकारी साझा नहीं कर सकता।"
    if status == "live_status":
        return "मैं अभी की उड़ान स्थिति, कतार या गेट काम कर रहे हैं या नहीं, यह जाँच नहीं सकता। कृपया अपनी एयरलाइन या एयरपोर्ट के कर्मचारियों से पूछें।"
    if status == "out_of_scope":
        return "मैं डिजी यात्रा से जुड़े पंजीकरण, बोर्डिंग पास, एयरपोर्ट की प्रक्रिया, गोपनीयता और ऐप की समस्याओं में मदद कर सकता हूँ। कृपया इन्हीं विषयों पर पूछें।"
    if "international" in english:
        return "मैं अंतरराष्ट्रीय यात्रा की मौजूदा उपलब्धता, पात्रता या किसी ट्रायल की पुष्टि नहीं कर सकता। यात्रा से पहले आधिकारिक डिजी यात्रा वेबसाइट और अपनी एयरलाइन से जाँचें: https://www.digiyatrafoundation.com/"
    if "airport list" in english or "supported-airport" in english:
        return "मैं अभी समर्थित एयरपोर्ट की सूची की पुष्टि नहीं कर सकता। यात्रा से पहले आधिकारिक सूची देखें: https://digiyatrafoundation.com/digi-yatra-implementation-current/"
    if "access your account" in english:
        return "मैं आपका खाता या अपलोड नहीं देख सकता। अपना बोर्डिंग पास और खाते की जानकारी डिजी यात्रा ऐप में जाँचें।"
    if "skip" in english:
        return "मैं पहचान सत्यापन को छोड़ने का तरीका नहीं बता सकता। कृपया ऐप में दिए गए सत्यापन चरणों का पालन करें।"
    return "इस डिजी यात्रा संबंधी जानकारी की पुष्टि के लिए मेरे पास पर्याप्त स्वीकृत प्रमाण नहीं हैं। आधिकारिक मार्गदर्शन या सहायता यहाँ देखें: https://www.digiyatrafoundation.com/"


def notice(text: str) -> str:
    if text.startswith("For your safety"):
        return "आपकी सुरक्षा के लिए व्यक्तिगत जानकारी हटाई गई है। इस चैट में ओटीपी, आधार नंबर, पासपोर्ट या बोर्डिंग पास साझा न करें।"
    if "sources differ" in text:
        return (
            "इस विषय पर स्रोतों में अंतर है। अधिक सावधानी वाला मार्गदर्शन दिया गया है; यात्रा से पहले एयरलाइन या एयरपोर्ट से पुष्टि करें।"
        )
    if "time-sensitive" in text:
        return "यह जानकारी समय के साथ बदल सकती है। यात्रा से पहले आधिकारिक डिजी यात्रा वेबसाइट पर जाँचें।"
    if "can't file" in text:
        return "मैं आपकी ओर से शिकायत दर्ज नहीं कर सकता। आधिकारिक सहायता से संपर्क करें और आधार नंबर या ओटीपी साझा न करें।"
    return text
