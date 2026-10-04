/** Turns Sarah's written reply into text that sounds natural when read aloud. */

const MAX_SPOKEN_CHARS = 600; // browsers cut off long utterances; the full text stays on screen

export function toSpokenText(reply: string): string {
  const lines = reply
    .replace(/\s*\(Synthetic\)/gi, "") // the on-screen banner already says the data is synthetic
    .split("\n")
    .map((raw) => {
      let l = raw.trim();
      if (!l) return "";
      l = l.replace(/^[•\-*]\s*/, "");
      l = l.replace(/^(\d+)\.\s+/, "Option $1: ");
      l = l.replace(/₹\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)/g, "$1 rupees"); // "1,250" yes; "500," (clause comma) no
      l = l.replace(/(\d+(?:\.\d+)?)\s?★/g, "$1 stars");
      l = l.replace(/\b1 min\b/g, "1 minute").replace(/\b(\d+) min\b/g, "$1 minutes");
      l = l.replace(/\s+×\s+/g, " ").replace(/\s+[—–]\s+/g, ", ");
      l = l.replace(/\s\+\s(delivery)/gi, " plus $1").replace(/\s=\s/g, ", total ");
      return /[.!?:]$/.test(l) ? l : `${l}.`;
    })
    .filter(Boolean);
  const spoken = lines.join(" ").replace(/\s{2,}/g, " ").trim();
  if (spoken.length <= MAX_SPOKEN_CHARS) return spoken;
  const cut = spoken.slice(0, MAX_SPOKEN_CHARS);
  const end = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("? "), cut.lastIndexOf("! "));
  return end > 120 ? cut.slice(0, end + 1) : cut;
}

export function recognitionErrorMessage(code: string): string | null {
  switch (code) {
    case "aborted":
      return null;
    case "not-allowed":
    case "service-not-allowed":
      return "Microphone access is blocked. Allow it in your browser's address bar, or type instead.";
    case "no-speech":
      return "I didn't hear anything. Tap the mic and try again.";
    case "audio-capture":
      return "No microphone was found on this device.";
    case "network":
      return "Voice input needs an internet connection in this browser. You can type instead.";
    default:
      return "Voice input stopped unexpectedly. You can type instead.";
  }
}

/** Prefers an Indian-English voice, then any English voice. */
export function pickVoice(voices: SpeechSynthesisVoice[], lang: string): SpeechSynthesisVoice | undefined {
  return (
    voices.find((v) => v.lang === lang) ??
    voices.find((v) => v.lang.replace("_", "-").toLowerCase() === lang.toLowerCase()) ??
    voices.find((v) => v.lang.toLowerCase().startsWith("en"))
  );
}
