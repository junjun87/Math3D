import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getProblemLesson } from "../services/api";

export default function ResultPage() {
  const { problemId } = useParams<{ problemId: string }>();
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!problemId) return;
    const poll = setInterval(async () => {
      try {
        const result = await getProblemLesson(problemId);
        if (result.status === "done" && result.lesson) {
          setData(result.lesson);
          clearInterval(poll);
        } else if (result.status === "error") {
          setErr(result.error_message || "计算失败");
          clearInterval(poll);
        }
      } catch (e: any) {
        setErr(e.message || "网络错误");
        clearInterval(poll);
      }
    }, 2000);
    return () => clearInterval(poll);
  }, [problemId]);

  return (
    <div style={{ padding: 16, fontFamily: "sans-serif" }}>
      <h2>Result Debug</h2>
      {err && <p style={{ color: "red" }}>Error: {err}</p>}
      {!data && !err && <p>Loading... (problem: {problemId})</p>}
      {data && (
        <pre style={{ fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
