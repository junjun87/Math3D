import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getProblemLesson, getLessonViewUrl, getLessonDownloadUrl } from "../services/api";

export default function ResultPage() {
  const { problemId } = useParams<{ problemId: string }>();
  const navigate = useNavigate();
  const [lesson, setLesson] = useState<any>(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    if (!problemId) return;
    const poll = setInterval(async () => {
      try {
        const result = await getProblemLesson(problemId);
        if (result.status === "done" && result.lesson) {
          setLesson(result.lesson);
          setStatus("done");
          clearInterval(poll);
        } else if (result.status === "error") {
          setStatus("error");
          clearInterval(poll);
        }
      } catch { /* retry */ }
    }, 2000);
    return () => clearInterval(poll);
  }, [problemId]);

  if (status === "loading") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center safe-bottom bg-white">
        <p className="text-lg text-gray-500">AI 正在计算...</p>
      </div>
    );
  }

  if (!lesson || status === "error") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center safe-bottom bg-white">
        <p className="text-red-500">计算失败</p>
        <button onClick={() => navigate("/")} className="mt-4 text-blue-500 underline">返回首页</button>
      </div>
    );
  }

  const kr = lesson.kernel_result;
  const steps = kr.steps || [];

  return (
    <div className="min-h-screen flex flex-col safe-bottom bg-gray-50">
      <header className="flex items-center gap-3 px-4 py-3 bg-white border-b sticky top-0 z-10">
        <button onClick={() => navigate("/")} className="text-gray-500 text-lg">← 返回</button>
        <h1 className="font-semibold">计算结果</h1>
        <div className="flex-1" />
        <span className="bg-green-100 text-green-700 text-xs px-2 py-1 rounded-full">
          {kr.body_type || ""}
        </span>
      </header>

      {/* 3D */}
      {lesson.id && (
        <div className="bg-white mx-4 mt-4 rounded-xl border overflow-hidden">
          <iframe
            src={getLessonViewUrl(lesson.id)}
            className="w-full aspect-square border-0"
            title="3D"
            sandbox="allow-scripts allow-same-origin"
          />
        </div>
      )}

      {/* 步骤 */}
      <div className="mx-4 mt-4">
        <h2 className="font-semibold text-lg mb-3">📝 解题步骤</h2>
        {steps.map((step: any, i: number) => (
          <div key={i} className="bg-white rounded-xl border p-4 mb-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-6 h-6 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">
                {step.step_number}
              </span>
              <h3 className="font-semibold text-blue-700 text-sm">{step.title}</h3>
            </div>
            <p className="text-sm text-gray-600 mb-2 whitespace-pre-wrap break-words">{step.description}</p>
            {step.formula && (
              <div className="bg-gray-50 rounded-lg p-3 mb-2 text-sm break-words">{step.formula}</div>
            )}
            {step.result && (
              <div className="bg-green-50 rounded-lg p-3 border border-green-200 text-sm break-words">{step.result}</div>
            )}
          </div>
        ))}
      </div>

      {/* 答案 */}
      {kr.answer && (
        <div className="mx-4 mt-4 mb-6">
          <h2 className="font-semibold text-lg mb-2">✨ 答案</h2>
          <div className="bg-gradient-to-r from-blue-500 to-blue-600 rounded-xl p-5 text-white text-center">
            <div className="text-2xl font-bold break-words">{kr.answer.latex || "N/A"}</div>
            {kr.answer.numeric !== undefined && (
              <div className="text-blue-100 text-sm mt-2">≈ {kr.answer.numeric.toFixed(4)}</div>
            )}
          </div>
        </div>
      )}

      {/* 下载 */}
      {lesson.id && (
        <div className="mx-4 mb-8 pb-4">
          <a href={getLessonDownloadUrl(lesson.id)} download
            className="block w-full text-center bg-white border border-blue-300 text-blue-600 rounded-xl py-3 font-semibold">
            📥 下载课件 HTML
          </a>
        </div>
      )}
    </div>
  );
}
