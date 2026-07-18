/**
 * KaTeX 公式渲染组件。
 */
import { useEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

interface LatexRendererProps {
  latex: string;
}

export function LatexRenderer({ latex }: LatexRendererProps) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (ref.current && latex) {
      try {
        katex.render(latex, ref.current, {
          displayMode: false,  // inline mode wraps on mobile
          throwOnError: false,
          trust: true,
          strict: false,
        });
      } catch (e) {
        ref.current.textContent = latex;
      }
    }
  }, [latex, display]);

  return <span ref={ref} className="break-words" />;
}
