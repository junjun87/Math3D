/**
 * 拍照 / 相册选择 / 文字输入页面。
 * 上传图片后跳转到确认页。
 */
import { useState, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { uploadImage, submitText } from "../services/api";
import { useAppStore } from "../stores/appStore";

export default function CapturePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const from = searchParams.get("from") || "camera";

  const [preview, setPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [textInput, setTextInput] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const setCurrentProblemId = useAppStore((s) => s.setCurrentProblemId);

  const handleFile = async (file: File) => {
    // 预览
    const url = URL.createObjectURL(file);
    setPreview(url);
    setError(null);

    // 压缩上传
    setUploading(true);
    try {
      const result = await uploadImage(file);
      setCurrentProblemId(result.problem_id);
      navigate(`/confirm/${result.problem_id}`);
    } catch (e: any) {
      setError(e.response?.data?.detail || "上传失败，请重试");
    } finally {
      setUploading(false);
    }
  };

  const handleCameraCapture = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  // 文字输入模式
  if (from === "text") {
    return (
      <div className="min-h-screen flex flex-col safe-bottom bg-white">
        <header className="flex items-center gap-3 px-4 py-3 border-b">
          <button onClick={() => navigate(-1)} className="text-gray-500 text-lg">
            ← 返回
          </button>
          <h1 className="font-semibold">文字输入题目</h1>
        </header>
        <div className="flex-1 p-4">
          <textarea
            className="w-full h-48 border rounded-xl p-4 text-sm focus:outline-none focus:ring-2 focus:ring-primary-400"
            placeholder="请输入题目内容，例如：&#10;在正方体 ABCD-A1B1C1D1 中，棱长为 2，求直线 AB1 与平面 A1C1D 的夹角。"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
          />
          <button
            disabled={!textInput.trim() || uploading}
            onClick={async () => {
              if (!textInput.trim()) return;
              setUploading(true);
              try {
                const result = await submitText(textInput.trim());
                setCurrentProblemId(result.problem_id);
                navigate(`/result/${result.problem_id}`);
              } catch (e: any) {
                setError(e.response?.data?.detail || "提交失败，请重试");
                setUploading(false);
              }
            }}
            className="w-full mt-4 bg-primary-500 disabled:bg-gray-300 text-white rounded-xl py-3 font-semibold"
          >
            {uploading ? "提交中..." : "提交题目"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-black safe-bottom">
      {/* 顶部栏 */}
      <header className="flex items-center justify-between px-4 py-3 bg-black/80 text-white">
        <button onClick={() => navigate(-1)}>← 返回</button>
        <h1 className="font-semibold">{from === "album" ? "选择图片" : "拍照搜题"}</h1>
        <div className="w-10" />
      </header>

      {/* 预览区 */}
      <div className="flex-1 flex items-center justify-center bg-gray-900">
        {preview ? (
          <img
            src={preview}
            alt="Preview"
            className="max-w-full max-h-full object-contain"
          />
        ) : (
          <div className="text-center text-gray-400">
            <div className="text-6xl mb-4">📷</div>
            <p>点击下方按钮拍照或选择图片</p>
          </div>
        )}
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-500 text-white text-center py-2 text-sm">
          {error}
        </div>
      )}

      {/* 操作按钮 */}
      <div className="bg-black/90 px-4 py-6 flex gap-3">
        {from === "album" ? (
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="flex-1 bg-primary-500 disabled:bg-gray-600 text-white rounded-xl py-4 font-semibold text-lg"
          >
            {uploading ? "上传中..." : "从相册选择"}
          </button>
        ) : (
          <>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="flex-1 bg-primary-500 disabled:bg-gray-600 text-white rounded-xl py-4 font-semibold text-lg"
            >
              {uploading ? "识别中..." : "📷 拍照"}
            </button>
            <button
              onClick={() => {
                fileRef.current!.setAttribute("capture", "");
                fileRef.current?.click();
              }}
              className="w-16 h-16 rounded-full bg-gray-700 text-white flex items-center justify-center"
            >
              🖼️
            </button>
          </>
        )}
      </div>

      {/* 隐藏的文件输入 */}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture={from !== "album" ? "environment" : undefined}
        onChange={handleCameraCapture}
        className="hidden"
      />
    </div>
  );
}
