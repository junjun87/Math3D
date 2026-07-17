/**
 * 上传 Hook — 管理上传状态和轮询。
 */
import { useState, useCallback } from "react";
import { uploadImage, getOcrResult } from "../services/api";

type UploadStatus = "idle" | "uploading" | "processing" | "done" | "error";

export function useUpload() {
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [problemId, setProblemId] = useState<string | null>(null);
  const [ocrText, setOcrText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(async (file: File) => {
    setStatus("uploading");
    setError(null);

    try {
      const result = await uploadImage(file);
      setProblemId(result.problem_id);
      setStatus("processing");

      // 轮询 OCR 结果
      const poll = setInterval(async () => {
        try {
          const ocr = await getOcrResult(result.problem_id);
          if (ocr.status === "ocr_done" || ocr.status === "confirmed") {
            setOcrText(ocr.ocr_raw_text || "");
            setStatus("done");
            clearInterval(poll);
          } else if (ocr.status === "error") {
            setError(ocr.error_message || "OCR 识别失败");
            setStatus("error");
            clearInterval(poll);
          }
        } catch {
          // 继续轮询
        }
      }, 2000);

      return result.problem_id;
    } catch (e: any) {
      setError(e.response?.data?.detail || "上传失败");
      setStatus("error");
      return null;
    }
  }, []);

  const reset = useCallback(() => {
    setStatus("idle");
    setProblemId(null);
    setOcrText("");
    setError(null);
  }, []);

  return { status, problemId, ocrText, error, upload, reset };
}
