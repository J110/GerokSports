"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import type { MatchState } from "../lib/types";

function deepMerge(prev: Record<string, unknown>, next: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = { ...prev };
  for (const key of Object.keys(next)) {
    const nv = next[key];
    const pv = prev[key];

    // Replace archived innings wholesale (never merge element-wise).
    if (key === "innings_history" && Array.isArray(nv)) {
      result[key] = nv;
      continue;
    }

    // Always prefer non-null incoming arrays (batting_card, bowling_card, etc.)
    if (Array.isArray(nv)) {
      result[key] = nv.length > 0 ? nv : (Array.isArray(pv) && pv.length > 0 ? pv : nv);
      continue;
    }

    // Deep-merge nested objects (match, scorecard, field, etc.)
    if (nv && typeof nv === "object" && !Array.isArray(nv) && pv && typeof pv === "object" && !Array.isArray(pv)) {
      result[key] = deepMerge(pv as Record<string, unknown>, nv as Record<string, unknown>);
      continue;
    }

    // For scalar values: prefer non-null/non-empty incoming, keep previous otherwise
    if (nv !== null && nv !== undefined && nv !== "") {
      result[key] = nv;
    }
    // else: keep pv (already in result from spread)
  }
  return result;
}

export function useMatchSocket(url: string) {
  const [state, setState] = useState<MatchState | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<number>(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const sessionRef = useRef<string | null>(null);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "state_update") {
        const newSession = data.session_id as string | undefined;
        if (newSession && sessionRef.current && newSession !== sessionRef.current) {
          console.log("[WS] Session changed — resetting state");
          setState(data as MatchState);
          sessionRef.current = newSession;
          setLastUpdate(Date.now());
          return;
        }
        if (newSession) sessionRef.current = newSession;

        setState((prev) => {
          if (!prev) return data as MatchState;
          return deepMerge(prev as unknown as Record<string, unknown>, data as Record<string, unknown>) as unknown as MatchState;
        });
        setLastUpdate(Date.now());
      }
    } catch {
      /* ignore malformed */
    }
  }, []);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        console.log("[WS] Connected");
      };

      ws.onmessage = handleMessage;

      ws.onclose = () => {
        setConnected(false);
        setState(null);
        sessionRef.current = null;
        reconnectRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      wsRef.current?.close();
      clearTimeout(reconnectRef.current);
    };
  }, [url, handleMessage]);

  return { state, connected, lastUpdate };
}
