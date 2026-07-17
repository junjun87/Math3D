/**
 * 题目确认页 — OCR 回显结果，用户可修正后确认。
 * 确认后触发服务端计算。
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getOcrResult, confirmProblem } from "../services/api";

export default function ConfirmPage() {
  const { problemId } = useParams<{ problemId: string }>();
  const navigate = useNavigate();

  const [ocrText, setOcrText] = useState<string>("");
  const [editingText, setEditingText] = useState<string>("");
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
