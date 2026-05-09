interface Props {
  balls: string[];
}

const EXTRAS = new Set(["wd", "Wd", "nb", "Nb", "NB", "WD", "lb", "Lb"]);
const EXTRA_COMPOUND_RE = /^(Wd|Nb|wd|nb)(\+\d+)?$/;

function isExtra(ball: string) {
  if (EXTRAS.has(ball)) return true;
  return EXTRA_COMPOUND_RE.test(ball);
}

function getBallStyle(ball: string) {
  const b = ball.toLowerCase();
  if (ball === "W") return "bg-[#F85149] text-white";
  if (ball === "4") return "bg-[#58A6FF] text-white";
  if (ball === "6") return "bg-[#D29922] text-white";
  if (ball === ".") return "bg-[#30363D] text-[#8B949E]";
  if (b === "wd" || b === "nb" || b === "lb")
    return "bg-[#30363D] text-[#D29922] text-[10px]";
  if (ball === "?") return "bg-[#21262D] text-[#484F58]";
  return "bg-[#30363D] text-[#E6EDF3]";
}

export default function ThisOver({ balls }: Props) {
  const legalCount = (balls || []).filter((b) => !isExtra(b)).length;
  const remaining = Math.max(0, 6 - legalCount);

  return (
    <div className="bg-[#161B22] rounded-lg border border-[#30363D] p-3 mt-2">
      <div className="text-xs text-[#8B949E] mb-2">This Over</div>
      {!balls || !balls.length ? (
        <div className="flex gap-1.5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="w-8 h-8 rounded-full flex items-center justify-center bg-[#21262D] border border-[#30363D]"
            />
          ))}
        </div>
      ) : (
        <div className="flex gap-1.5 flex-wrap items-center">
          {balls.map((ball, i) => (
            <div
              key={i}
              className={`${
                isExtra(ball) ? "w-7 h-7" : "w-8 h-8"
              } rounded-full flex items-center justify-center text-xs font-mono font-bold ${getBallStyle(ball)}`}
            >
              {ball}
            </div>
          ))}
          {remaining > 0 &&
            Array.from({ length: remaining }).map((_, i) => (
              <div
                key={`rem-${i}`}
                className="w-8 h-8 rounded-full flex items-center justify-center bg-[#21262D] border border-dashed border-[#30363D]"
              />
            ))}
        </div>
      )}
    </div>
  );
}
