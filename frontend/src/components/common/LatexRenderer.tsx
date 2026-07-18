import React, { useEffect, useRef, useState } from "react";

interface Props {
  latex: string;
  block?: boolean;
}

export function LatexRenderer({ latex, block }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [katexLib, setKatexLib] = useState<any>(null);

  useEffect(() => {
    let cancelled = false;
    import("katex")
      .then((m) => { if (!cancelled) setKatexLib(() => m.default || m); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!ref.current || !latex) return;
    if (katexLib) {
      try {
        katexLib.render(latex, ref.current, {
          displayMode: !!block,
          throwOnError: false,
          trust: true,
          strict: false,
        });
      } catch {
        ref.current.textContent = latex;
      }
    } else {
      ref.current.textContent = latex;
    }
  }, [latex, block, katexLib]);

  return block
    ? <div ref={ref as any} className="break-words" />
    : <span ref={ref as any} className="break-words" />;
}
