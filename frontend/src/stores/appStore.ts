/**
 * Math3D 全局状态管理 (Zustand)。
 */
import { create } from "zustand";
import type { LessonData, ProblemDetail } from "../types/api";

type UploadState =
  | "idle"
  | "capturing"
  | "uploading"
  | "processing"
  | "completed"
  | "error";

interface AppState {
  // 上传状态机
  uploadState: UploadState;
  currentProblemId: string | null;
  uploadError: string | null;

  // 当前查看结果
  currentLesson: LessonData | null;
  currentProblem: ProblemDetail | null;

  // Actions
  setUploadState: (state: UploadState) => void;
  setCurrentProblemId: (id: string | null) => void;
  setUploadError: (error: string | null) => void;
  setCurrentLesson: (lesson: LessonData | null) => void;
  setCurrentProblem: (problem: ProblemDetail | null) => void;
  reset: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  uploadState: "idle",
  currentProblemId: null,
  uploadError: null,
  currentLesson: null,
  currentProblem: null,

  setUploadState: (uploadState) => set({ uploadState }),
  setCurrentProblemId: (currentProblemId) => set({ currentProblemId }),
  setUploadError: (uploadError) => set({ uploadError }),
  setCurrentLesson: (currentLesson) => set({ currentLesson }),
  setCurrentProblem: (currentProblem) => set({ currentProblem }),
  reset: () =>
    set({
      uploadState: "idle",
      currentProblemId: null,
      uploadError: null,
      currentLesson: null,
      currentProblem: null,
    }),
}));
