/**
 * 历史记录页 — 查看已解答的题目列表。
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getHistory } from "../services/api";
import type { ProblemSummary } from "../types/api";

export default function HistoryPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ProblemSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const result = await getHistory({ limit: 50 });
      setItems(result.items);
    } catch (e) {
      console.error("加载历史记录失败:", e);
    } finally {
      setLoading(false);
    }
  };

  const statusLabel = (status: string) => {
    const map: Record<string, string> = {
      uploaded: "已上传",
      ocr_done: "已识别",
      confirmed: "已确认",
      computing: "计算中",
      done: "已完成",
      error: "失败",
    };
    return map[status] || status;
  };

  const statusColor = (status: string) => {
    const map: Record<string, string> = {
      uploaded: "bg-gray-100 text-gray-600",
      ocr_done: "bg-blue-100 text-blue-600",
      confirmed: "bg-yellow-100 text-yellow-700",
      computing: "bg-purple-100 text-purple-600",
      done: "bg-green-100 text-green-600",
      error: "bg-red-100 text-red-600",
    };
    return map[status] || "bg-gray-100 text-gray-600";
  };

  return (
    <div className="min-h-screen flex flex-col safe-bottom bg-gray-50">
      <header className="flex items-center gap-3 px-4 py-3 bg-white border-b">
        <button onClick={() => navigate(-1)} className="text-gray-500 text-lg">
          ← 返回
        </button>
        <h1 className="font-semibold">历史记录</h1>
      </header>

      <div className="flex-1 p-4">
        {loading ? (
          <div className="text-center py-12 text-gray-400">加载中...</div>
        ) : items.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-5xl mb-4">📭</div>
            <p className="text-gray-400">暂无记录</p>
            <button
              onClick={() => navigate("/capture")}
              className="mt-4 text-primary-500 underline"
            >
              去拍照搜题
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {items.map((item) => (
              <div
                key={item.id}
                onClick={() => {
                  if (item.status === "done") navigate(`/result/${item.id}`);
                  else if (item.status === "ocr_done" || item.status === "confirmed")
                    navigate(`/confirm/${item.id}`);
                }}
                className="bg-white rounded-xl border p-4 active:bg-gray-50 cursor-pointer"
              >
                <div className="flex items-start gap-3">
                  {item.thumbnail_url ? (
                    <img
                      src={item.thumbnail_url}
                      alt=""
                      className="w-16 h-16 rounded-lg object-cover bg-gray-100"
                    />
                  ) : (
                    <div className="w-16 h-16 rounded-lg bg-gray-100 flex items-center justify-center text-gray-300">
                      📷
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium line-clamp-2">
                      {item.ocr_summary || "题目内容待识别"}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${statusColor(item.status)}`}
                      >
                        {statusLabel(item.status)}
                      </span>
                      {item.subject && (
                        <span className="text-xs text-gray-400">{item.subject}</span>
                      )}
                    </div>
                  </div>
                  <span className="text-gray-300">→</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
