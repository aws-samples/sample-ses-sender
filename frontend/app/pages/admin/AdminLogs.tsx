"use client";
import React, { useState, useEffect, useRef } from "react";
import { API, authH, useAuth, useToast, Card, Btn } from "../../components/shared";
import { useT } from "../../i18n";

export default function AdminLogs() {
  const { token } = useAuth();
  const { toast } = useToast();
  const t = useT();
  const [lines, setLines] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [lineCount, setLineCount] = useState(500);
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/admin/logs?lines=${lineCount}`, { headers: authH(token) });
      if (r.ok) {
        const data = await r.json();
        setLines(data.lines || []);
      } else {
        toast("error", "Failed to load logs");
      }
    } catch {
      toast("error", "Network error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchLogs(); }, [lineCount]);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  const downloadLogs = async () => {
    try {
      const r = await fetch(`${API}/admin/logs/download?lines=10000`, { headers: authH(token) });
      if (r.ok) {
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const disposition = r.headers.get("content-disposition") || "";
        const match = disposition.match(/filename="(.+)"/);
        a.download = match ? match[1] : "ses-sender-logs.log";
        a.click();
        URL.revokeObjectURL(url);
      } else {
        toast("error", "Download failed");
      }
    } catch {
      toast("error", "Network error");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={lineCount}
          onChange={(e) => setLineCount(Number(e.target.value))}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value={100}>100 lines</option>
          <option value={500}>500 lines</option>
          <option value={1000}>1000 lines</option>
          <option value={5000}>5000 lines</option>
        </select>
        <Btn onClick={fetchLogs} disabled={loading}>
          {loading ? "Loading..." : "🔄 Refresh"}
        </Btn>
        <Btn onClick={downloadLogs}>📥 Download</Btn>
        <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer ml-auto">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="rounded"
          />
          Auto scroll
        </label>
      </div>

      <div
        ref={containerRef}
        className="bg-gray-900 text-gray-100 font-mono text-xs leading-5 rounded-xl p-4 overflow-auto border border-gray-700"
        style={{ height: "calc(100vh - 220px)" }}
      >
        {lines.length === 0 ? (
          <div className="text-gray-500 text-center py-10">No logs available</div>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="hover:bg-gray-800/50 px-1 whitespace-pre-wrap break-all">
              <span className="text-gray-500 select-none mr-2 inline-block w-10 text-right">{i + 1}</span>
              <span className={
                line.includes("ERROR") ? "text-red-400" :
                line.includes("WARNING") ? "text-yellow-400" :
                line.includes("INFO") ? "text-green-300" :
                "text-gray-300"
              }>{line}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
