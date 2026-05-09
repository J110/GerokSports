"use client";
import { useState, useEffect, useRef } from "react";

export interface CommentaryEntry {
  persona: "wire" | "storyteller" | "analyst" | "colour";
  text: string;
  timestamp: number;
  over: string;
  score: string;
  latency_ms?: number;
}

export function useCommentarySocket(url: string) {
  const [entries, setEntries] = useState<CommentaryEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "commentary" && data.entry) {
            setEntries((prev) => [data.entry, ...prev].slice(0, 100));
          }
        } catch {}
      };

      ws.onclose = () => {
        setConnected(false);
        reconnectRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [url]);

  return { entries, connected };
}
