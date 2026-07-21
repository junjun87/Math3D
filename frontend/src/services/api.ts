/**
 * Math3D API 客户端。
 * 封装所有后端 API 请求。
 */
import axios from "axios";
import type { ProblemDetail, LessonData, ProblemSummary, OcrResult } from "../types/api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// ========== 上传 ==========

export async function uploadImage(file: File): Promise<{
  problem_id: string;
  status: string;
  image_url: string;
  thumbnail_url: string;
}> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post("/problems/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function submitText(text: string): Promise<{
  problem_id: string;
  status: string;
  message: string;
}> {
  const { data } = await client.post("/problems/text", { text });
  return data;
}

// ========== 题目 ==========

export async function getProblem(problemId: string): Promise<ProblemDetail> {
  const { data } = await client.get(`/problems/${problemId}`);
  return data;
}

export async function getOcrResult(problemId: string): Promise<OcrResult> {
  const { data } = await client.get(`/problems/${problemId}/ocr`);
  return data;
}

export async function confirmProblem(
  problemId: string,
  correctedText?: string
): Promise<{ problem_id: string; status: string; message: string }> {
  const { data } = await client.post(`/problems/${problemId}/confirm`, {
    corrected_text: correctedText || "",
  });
  return data;
}

// ========== 课件 ==========

export async function getProblemLesson(problemId: string): Promise<{
  problem_id: string;
  status: string;
  has_lesson: boolean;
  lesson: LessonData | null;
  error_message: string | null;
}> {
  const { data } = await client.get(`/problems/${problemId}/lesson`);
  return data;
}

export async function getLesson(lessonId: string): Promise<LessonData> {
  const { data } = await client.get(`/lessons/${lessonId}`);
  return data;
}

export function getLessonViewUrl(lessonId: string): string {
  return `${API_BASE}/lessons/${lessonId}/view`;
}

export function getLessonDownloadUrl(lessonId: string): string {
  return `${API_BASE}/lessons/${lessonId}/download`;
}

// ========== 历史 ==========

export async function getHistory(params?: {
  user_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<{
  items: ProblemSummary[];
  total: number;
  limit: number;
  offset: number;
}> {
  const { data } = await client.get("/history", { params });
  return data;
}

// ========== 健康检查 ==========

export async function healthCheck(): Promise<{
  status: string;
  app: string;
  version: string;
}> {
  const { data } = await client.get("/health");
  return data;
}
