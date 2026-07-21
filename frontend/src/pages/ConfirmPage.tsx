/**
 * 题目确认页 — OCR 回显结果，用户可修正后确认。
 * 确认后触发服务端计算。
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getOcrResult, confirmProblem } from "../services/api";
import { LatexRenderer } from "../components/common/LatexRenderer";
import type { OcrBlock } from "../types/api";

export default function ConfirmPage() {
  const { problemId } = useParams<{ problemId: string }>();
  const navigate = useNavigate();

  const [ocrText, setOcrText] = useState<string>("");
  const [editingText, setEditingText] = useState<string>("");
  const [ocrBlocks, setOcrBlocks] = useState<OcrBlock[]>([]);
  const [reviewRequired, setReviewRequired] = useState(false);
  const [status, setStatus] = useState<string>("uploaded");
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!problemId) return;

    const poll = setInterval(async () => {
      try {
        const result = await getOcrResult(problemId);
        setStatus(result.status);

        if (result.status === "ocr_done" || result.status === "confirmed") {
          setOcrText(result.ocr_raw_text || "");
          setEditingText(result.ocr_raw_text || "");
          setOcrBlocks(result.ocr_blocks || []);
          setReviewRequired(result.ocr_review_required);
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

  const handleConfirm = async () => {
    if (!problemId) return;
    setConfirming(true);
    try {
      const result = await confirmProblem(problemId, editingText);
      if (result.status === "confirmed") {
        navigate(`/result/${problemId}`);
      }
    } catch {
      setConfirming(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center safe-bottom bg-white">
        <div className="animate-spin text-4xl mb-4">⏳</div>
        <p className="text-gray-500">AI 正在识别题目...</p>
        <p className="text-gray-300 text-sm mt-2">请稍候</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col safe-bottom bg-white">
      <header className="flex items-center gap-3 px-4 py-3 border-b">
        <button onClick={() => navigate(-1)} className="text-gray-500 text-lg">
          ← 返回
        </button>
        <h1 className="font-semibold">确认题目</h1>
      </header>

      <div className="flex-1 p-4 flex flex-col gap-4">
        <div className="bg-blue-50 rounded-xl p-4 text-sm text-blue-700">
          💡 AI 已识别出以下题目内容，请核对。如有错误可直接修改。
        </div>

        {reviewRequired && (
          <div className="bg-amber-50 rounded-xl p-4 text-sm text-amber-800">
            检测到置信度较低或符号不完整的内容，请重点核对下方标记的公式和字符。
          </div>
        )}

        {status === "error" ? (
          <div className="bg-red-50 rounded-xl p-4 text-red-600">
            OCR 识别失败，请返回重新上传更清晰的图片。
          </div>
        ) : (
          <>
            {/* 可编辑的识别结果 */}
            <textarea
              className="w-full h-40 border rounded-xl p-4 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary-400"
              value={editingText}
              onChange={(e) => setEditingText(e.target.value)}
            />

            {ocrBlocks.some((block) => block.is_formula || block.risk_flags.length > 0) && (
              <section className="rounded-xl border border-gray-200 p-3">
                <h2 className="text-sm font-semibold text-gray-700">公式与待核对内容</h2>
                <div className="mt-3 space-y-3">
                  {ocrBlocks
                    .filter((block) => block.is_formula || block.risk_flags.length > 0)
                    .map((block, index) => (
                      <div
                        key={`${block.line}-${index}`}
                        className={`rounded-lg p-3 text-sm ${block.risk_flags.length ? "bg-amber-50" : "bg-gray-50"}`}
                      >
                        <div className="flex items-center justify-between gap-2 text-xs text-gray-500">
                          <span>{block.is_formula ? "公式" : "文本"}</span>
                          <span>置信度 {Math.round(block.confidence * 100)}%</span>
                        </div>
                        {block.is_formula ? (
                          <div className="mt-2 overflow-x-auto text-base">
                            <LatexRenderer latex={block.text} block />
                          </div>
                        ) : (
                          <p className="mt-2 text-gray-800">{block.text}</p>
                        )}
                        <p className="mt-2 break-words font-mono text-xs text-gray-500">原始识别：{block.text}</p>
                        {block.risk_flags.length > 0 && (
                          <p className="mt-1 text-xs text-amber-700">待核对：{block.risk_flags.join("、")}</p>
                        )}
                      </div>
                    ))}
                </div>
              </section>
            )}

            {/* 原图查看 */}
            <div className="text-xs text-gray-400">
              原 OCR 识别结果: {ocrText || "(空)"}
            </div>
          </>
        )}
      </div>

      {/* 确认按钮 */}
      <div className="px-4 py-4 border-t">
        <button
          onClick={handleConfirm}
          disabled={confirming || status === "error" || !editingText.trim()}
          className="w-full bg-primary-500 disabled:bg-gray-300 text-white rounded-xl py-4 font-semibold text-lg"
        >
          {confirming ? "提交中..." : "确认并开始计算"}
        </button>
      </div>
    </div>
  );
}
