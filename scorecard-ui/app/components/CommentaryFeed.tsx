"use client";
import type { CommentaryEntry } from "../hooks/useCommentarySocket";

const PERSONA_STYLES: Record<
  string,
  { label: string; color: string; bg: string; icon: string; border: string }
> = {
  wire: {
    label: "Wire",
    color: "text-[#8B949E]",
    bg: "bg-[#161B22]",
    icon: "📰",
    border: "border-[#30363D]",
  },
  storyteller: {
    label: "Storyteller",
    color: "text-[#E6EDF3]",
    bg: "bg-[#161B22]",
    icon: "🎙️",
    border: "border-[#58A6FF]/30",
  },
  analyst: {
    label: "Analyst",
    color: "text-[#58A6FF]",
    bg: "bg-[#0D1117]",
    icon: "📊",
    border: "border-[#58A6FF]/50",
  },
  colour: {
    label: "Colour",
    color: "text-[#D29922]",
    bg: "bg-[#161B22]",
    icon: "🌟",
    border: "border-[#D29922]/50",
  },
};

interface Props {
  entries: CommentaryEntry[];
  activePersonas: Set<string>;
  onTogglePersona: (p: string) => void;
  connected: boolean;
}

export default function CommentaryFeed({
  entries,
  activePersonas,
  onTogglePersona,
  connected,
}: Props) {
  const filtered = entries.filter((e) => activePersonas.has(e.persona));

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-3">
        <div className="flex gap-2 flex-wrap">
          {Object.entries(PERSONA_STYLES).map(([key, style]) => (
            <button
              key={key}
              onClick={() => onTogglePersona(key)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
                activePersonas.has(key)
                  ? `${style.bg} ${style.color} ${style.border} border`
                  : "bg-[#0D1117] text-[#484F58] border-[#30363D]"
              }`}
            >
              {style.icon} {style.label}
            </button>
          ))}
        </div>
        <div
          className={`w-2 h-2 rounded-full ${
            connected ? "bg-green-500" : "bg-red-500"
          }`}
          title={connected ? "Commentary connected" : "Commentary disconnected"}
        />
      </div>

      <div className="space-y-2">
        {filtered.length === 0 && (
          <div className="text-center text-[#8B949E] text-sm py-8">
            {connected
              ? "Waiting for the next delivery..."
              : "Connecting to commentary engine..."}
          </div>
        )}

        {filtered.map((entry, i) => {
          const style = PERSONA_STYLES[entry.persona];
          if (!style) return null;
          return (
            <div
              key={`${entry.timestamp}-${entry.persona}-${i}`}
              className={`${style.bg} rounded-lg border ${style.border} p-3`}
            >
              <div className="flex justify-between items-center mb-1">
                <span className={`text-xs font-medium ${style.color}`}>
                  {style.icon} {style.label}
                </span>
                <span className="text-xs text-[#8B949E]">
                  {entry.over} · {entry.score}
                </span>
              </div>
              <p
                className={`text-sm leading-relaxed ${
                  entry.persona === "colour"
                    ? "text-[#E6EDF3] italic"
                    : entry.persona === "wire"
                      ? "text-[#8B949E] font-mono text-xs"
                      : "text-[#E6EDF3]"
                }`}
              >
                {entry.text}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
