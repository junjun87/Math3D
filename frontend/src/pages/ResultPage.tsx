/**
 * 课件结果页 — 展示交互式 3D 课件、分步解析和最终答案。
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getProblemLesson, getLessonViewUrl, getLessonDownloadUrl } from "../services/api";
import type { LessonData } from "../types/api";
import { LatexRenderer } from "../components/common/LatexRenderer";

export default function ResultPage() {
  const { problemId } = useParams<{ problemId: string }>();
  const navigate = useNavigate();

  const [lesson, setLesson] = useState<LessonData | null>(null);
  const [status, setStatus] = useState<string>("computing");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!problemId) return;

    const poll = setInterval(async () => {
      try {
        const result = await getProblemLesson(problemId);
        setStatus(result.status);

        if (result.status === "done" && result.lesson) {
          setLesson(result.lesson);
          setLoading(false);
          clearInterval(poll);
        } else if (result.status === "error") {
          setLoading(false);
          clearInterval(poll);
        }
      } catch {
        // 继续轮询
      }
    }, 2000);

    return () => clearInterval(poll);
  }, [problemId]);

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center safe-bottom bg-white">
        <div className="animate-spin text-4xl mb-4">🔢</div>
        <p className="text-gray-500">AI 正在计算答案...</p>
        <p className="text-gray-300 text-sm mt-2">正在进行符号计算</p>
      </div>
    );
  }

  if (!lesson) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center safe-bottom bg-white">
        <p className="text-red-500">计算失败</p>
        <button onClick={() => navigate(-1)} className="mt-4 text-primary-500 underline">
          返回重试
        </button>
      </div>
    );
  }

  const { kernel_result: kr } = lesson;
  const steps = kr.steps || [];
  const answer = kr.answer;

  return (
    <div className="min-h-screen flex flex-col safe-bottom bg-gray-50">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 py-3 bg-white border-b sticky top-0 z-10">
        <button onClick={() => navigate(-1)} className="text-gray-500 text-lg">
          ← 返回
        </button>
        <h1 className="font-semibold">计算结果</h1>
        <div className="flex-1" />
        <span className="bg-green-100 text-green-700 text-xs px-2 py-1 rounded-full">
          {kr.body_type === "cube" ? "正方体" : kr.body_type}
        </span>
      </header>

      {/* 3D 交互课件 */}
      {lesson?.id && (
        <div className="bg-white mx-4 mt-4 rounded-xl border overflow-hidden">
          <iframe
            src={getLessonViewUrl(lesson.id)}
            className="w-full aspect-square border-0"
            title="3D 交互课件"
            sandbox="allow-scripts allow-same-origin"
          />
        </div>
      )}

      {/* 分步解析 — 全部展开 */}
      <div className="mx-4 mt-4">
        <h2 className="font-semibold text-lg mb-3">📝 解题步骤</h2>
        {steps.map((step, i) => (
          <div key={i} className="bg-white rounded-xl border p-4 mb-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-6 h-6 rounded-full bg-primary-500 text-white text-xs flex items-center justify-center font-bold">
                {step.step_number}
              </span>
              <h3 className="font-semibold text-primary-700 text-sm">
                {step.title}
              </h3>
            </div>
            <p className="text-sm text-gray-600 mb-2 break-words">
              {step.description}
            </p>
            {step.formula && (
              <div className="bg-gray-50 rounded-lg p-3 mb-2 break-words">
                <LatexRenderer latex={step.formula} display />
              </div>
            )}
            {step.result && (
              <div className="bg-green-50 rounded-lg p-3 border border-green-200 break-words">
                <LatexRenderer latex={step.result} display />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 答案卡片 */}
      {answer && (
        <div className="mx-4 mt-4 mb-6">
          <h2 className="font-semibold text-lg mb-2">✨ 答案</h2>
          <div className="bg-gradient-to-r from-primary-500 to-primary-600 rounded-xl p-5 text-white">
            <div className="text-center">
              <div className="text-2xl font-bold overflow-x-auto">
                <LatexRenderer latex={answer.latex} display />
              </div>
              {answer.numeric !== undefined && (
                <div className="text-primary-100 text-sm mt-2">
                  约等于 {answer.numeric.toFixed(4)}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 下载按钮 */}
      {lesson?.id && (
        <div className="mx-4 mb-8">
          <a
            href={getLessonDownloadUrl(lesson.id)}
            className="block w-full text-center bg-white border border-primary-300 text-primary-600 rounded-xl py-3 font-semibold"
            download
          >
            📥 下载课件 HTML（离线可用）
          </a>
        </div>
      )}
    </div>
  );
}
