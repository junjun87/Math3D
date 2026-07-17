/**
 * 分步导航组件 — 显示解题步骤的序号列表，可点击切换。
 */
import type { SolutionStep } from "../../types/api";

interface StepNavigationProps {
  steps: SolutionStep[];
  activeStep: number;
  onStepChange: (index: number) => void;
}

export function StepNavigation({ steps, activeStep, onStepChange }: StepNavigationProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {steps.map((step, i) => (
        <button
          key={i}
          onClick={() => onStepChange(i)}
          className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
            i === activeStep
              ? "bg-primary-500 text-white shadow"
              : "bg-white text-gray-600 border hover:bg-gray-50"
          }`}
        >
          步骤 {step.step_number}
        </button>
      ))}
    </div>
  );
}
