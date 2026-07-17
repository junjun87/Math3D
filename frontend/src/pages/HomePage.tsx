/**
 * 首页 — 提供拍照、相册、文字输入三种入口。
 */
import { useNavigate } from "react-router-dom";

export default function HomePage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-b from-blue-50 to-white safe-bottom">
      {/* Header */}
      <header className="text-center pt-12 pb-6 px-4">
        <h1 className="text-3xl font-bold text-primary-700">Math3D</h1>
        <p className="mt-2 text-gray-500 text-sm">
          拍照搜题 · AI 解析 · 交互式 3D 课件
        </p>
      </header>

      {/* 入口卡片 */}
      <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6 pb-8">
        {/* 拍照 */}
        <button
          onClick={() => navigate("/capture")}
          className="w-full max-w-sm flex items-center gap-4 bg-primary-500 hover:bg-primary-600 active:scale-[0.98] text-white rounded-2xl p-5 shadow-lg shadow-primary-200 transition-all"
        >
          <span className="text-3xl">📷</span>
          <div className="text-left">
            <div className="font-semibold text-lg">拍照搜题</div>
            <div className="text-primary-100 text-sm">拍摄题目照片，AI 自动识别</div>
          </div>
        </button>

        {/* 相册 */}
        <button
          onClick={() => navigate("/capture?from=album")}
          className="w-full max-w-sm flex items-center gap-4 bg-white hover:bg-gray-50 active:scale-[0.98] text-gray-800 rounded-2xl p-5 shadow border border-gray-100 transition-all"
        >
          <span className="text-3xl">🖼️</span>
          <div className="text-left">
            <div className="font-semibold text-lg">从相册选择</div>
            <div className="text-gray-400 text-sm">上传已有的题目截图</div>
          </div>
        </button>

        {/* 文字输入 */}
        <button
          onClick={() => navigate("/capture?from=text")}
          className="w-full max-w-sm flex items-center gap-4 bg-white hover:bg-gray-50 active:scale-[0.98] text-gray-800 rounded-2xl p-5 shadow border border-gray-100 transition-all"
        >
          <span className="text-3xl">⌨️</span>
          <div className="text-left">
            <div className="font-semibold text-lg">文字输入</div>
            <div className="text-gray-400 text-sm">手动输入题目内容</div>
          </div>
        </button>

        {/* 历史记录 */}
        <button
          onClick={() => navigate("/history")}
          className="w-full max-w-sm flex items-center gap-4 bg-white hover:bg-gray-50 active:scale-[0.98] text-gray-800 rounded-2xl p-5 shadow border border-gray-100 transition-all"
        >
          <span className="text-3xl">📋</span>
          <div className="text-left">
            <div className="font-semibold text-lg">历史记录</div>
            <div className="text-gray-400 text-sm">查看已解答的题目</div>
          </div>
        </button>
      </div>

      {/* Footer */}
      <footer className="text-center py-4 text-gray-300 text-xs">
        Math3D v0.1.0
      </footer>
    </div>
  );
}
