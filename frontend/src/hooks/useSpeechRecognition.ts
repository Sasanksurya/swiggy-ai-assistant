"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { recognitionErrorMessage } from "@/lib/speech";

interface RecognitionResult {
  isFinal: boolean;
  0: { transcript: string };
}
interface RecognitionEvent {
  resultIndex: number;
  results: { length: number; [i: number]: RecognitionResult };
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

function getCtor(): RecognitionCtor | undefined {
  if (typeof window === "undefined") return undefined;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

const subscribeNothing = () => () => {};

export interface UseSpeechRecognitionOptions {
  lang?: string;
  /** Called once with the final transcript of each utterance. */
  onFinal: (text: string) => void;
}

export function useSpeechRecognition({ lang = "en-IN", onFinal }: UseSpeechRecognitionOptions) {
  // false on the server and during hydration, then the real answer: no hydration mismatch, no flash of "unsupported"
  const supported = useSyncExternalStore(subscribeNothing, () => !!getCtor(), () => false);
  const checked = useSyncExternalStore(subscribeNothing, () => true, () => false);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<Recognition | null>(null);
  const deliveredRef = useRef(false);
  const onFinalRef = useRef(onFinal);
  useEffect(() => {
    onFinalRef.current = onFinal;
  });

  useEffect(() => () => recRef.current?.abort(), []);

  const start = useCallback(() => {
    const Ctor = getCtor();
    if (!Ctor || recRef.current) return;
    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    deliveredRef.current = false;
    setError(null);
    setInterim("");

    rec.onstart = () => setListening(true);
    rec.onresult = (e) => {
      let live = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) {
          const text = r[0].transcript.trim();
          if (text && !deliveredRef.current) {
            deliveredRef.current = true;
            setInterim("");
            onFinalRef.current(text);
          }
        } else {
          live += r[0].transcript;
        }
      }
      if (!deliveredRef.current) setInterim(live);
    };
    rec.onerror = (e) => setError(recognitionErrorMessage(e.error));
    rec.onend = () => {
      recRef.current = null;
      setListening(false);
      setInterim("");
    };

    recRef.current = rec;
    try {
      rec.start();
    } catch {
      recRef.current = null;
      setError(recognitionErrorMessage("unknown"));
    }
  }, [lang]);

  const stop = useCallback(() => recRef.current?.stop(), []);

  return { supported, checked, listening, interim, error, start, stop, clearError: () => setError(null) };
}
