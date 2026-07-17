/**
 * KaTeX 公式渲染组件。
 */
import { useEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

interface LatexRendererProps {
  latex: string;
  display?: boolean;
}

export function LatexRenderer({ latex, display = false }: LatexRendererProps) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (ref.current && latex) {
      try {
        katex.render(latex, ref.current, {
          displayMode: display,
          throwOnError: false,
          trust: true,
        });
      } catch (e) {
        ref.current.textContent = latex;
      }
    }
  }, [latex, display]);

  return <span ref={ref} />;
}
