/** API 响应类型定义 */

export interface ProblemSummary {
  id: string;
  user_id: string | null;
  image_url: string;
  thumbnail_url: string | null;
  status: ProblemStatus;
  subject: string | null;
  ocr_summary: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export type ProblemStatus =
  | "uploaded"
  | "ocr_done"
  | "confirmed"
  | "computing"
  | "done"
  | "error";

export interface ProblemDetail extends ProblemSummary {
  structured_json: StructuredProblem | null;
  ocr_raw_text: string | null;
  ocr_confidence: number | null;
}

export interface OcrBlock {
  text: string;
  confidence: number;
  is_formula: boolean;
  bbox: unknown[];
  bbox_rect: [number, number, number, number] | null;
  line: number;
  risk_flags: string[];
}

export interface OcrResult {
  problem_id: string;
  status: string;
  ocr_raw_text: string | null;
  ocr_confidence: number | null;
  ocr_blocks: OcrBlock[];
  ocr_source: string | null;
  ocr_review_required: boolean;
  error_message: string | null;
}

export interface StructuredProblem {
  subject: string;
  body_type: string;
  description: string;
  question: string;
  given: Record<string, unknown>;
  target: {
    type: string;
    [key: string]: unknown;
  };
  language: string;
}

export interface LessonData {
  id: string;
  problem_id: string;
  subject: string;
  kernel_result: KernelResult;
  created_at: string;
}

export interface KernelResult {
  subject: string;
  body_type: string;
  problem_type: string;
  answer: {
    latex: string;
    exact: string;
    numeric?: number;
    angle_latex?: string;
  };
  steps: SolutionStep[];
  model_3d: Model3D | null;
}

export interface SolutionStep {
  step_number: number;
  title: string;
  description: string;
  formula: string;
  result: string;
}

export interface Model3D {
  points: Record<string, [number, number, number]>;
  edges: [string, string][];
  faces: [string, string[]][] | null;
  scale: number;
}

export interface TaskStatus {
  task_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;
  result?: {
    problem_id: string;
    structured_problem: StructuredProblem;
    subject: string;
  };
}
