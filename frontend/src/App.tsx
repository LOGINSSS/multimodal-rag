import { useCallback, useEffect, useRef, useState } from "react";
import { ask, health, submitIngest, taskStatus } from "./api";
import { Composer } from "./components/Composer";
import { Message } from "./components/Message";
import { ThemeToggle } from "./components/ThemeToggle";
import type { Message as MessageType, Theme, UploadItem } from "./types";

const SUGGESTIONS = [
  "这个项目用了哪些模型？",
  "什么是 RRF 混合检索？",
  "总结一下我的知识库",
];

let idCounter = 0;
const nextId = () => `m${++idCounter}`;
let uploadCounter = 0;
const nextUploadId = () => `u${++uploadCounter}`;

function getInitialTheme(): Theme {
  const saved = localStorage.getItem("rag-theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [rows, setRows] = useState<number | null>(null);
  const [online, setOnline] = useState(false);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const dragDepth = useRef(0);

  // 应用主题到 <html>
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("rag-theme", theme);
  }, [theme]);

  // 启动时检查后端健康
  useEffect(() => {
    health()
      .then((h) => {
        setOnline(h.milvus_ok);
        setRows(h.rows);
      })
      .catch(() => setOnline(false));
  }, []);

  // 新消息自动滚动到底部
  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const showToast = useCallback((text: string) => {
    setToast(text);
    window.setTimeout(() => setToast(null), 3200);
  }, []);

  const refreshHealth = useCallback(() => {
    health()
      .then((h) => {
        setRows(h.rows);
        setOnline(h.milvus_ok);
      })
      .catch(() => setOnline(false));
  }, []);

  // 轮询单个入库任务，直到 done/failed
  const pollTask = useCallback(
    (taskId: string, itemId: string) => {
      taskStatus(taskId)
        .then((st) => {
          setUploads((prev) =>
            prev.map((u) =>
              u.id === itemId
                ? { ...u, status: st.status, inserted: st.inserted, error: st.error }
                : u
            )
          );
          if (st.status === "pending" || st.status === "running") {
            setTimeout(() => pollTask(taskId, itemId), 1500);
          } else {
            refreshHealth();
            showToast(
              st.status === "done"
                ? `已入库「${st.source}」${st.inserted} 个片段`
                : `「${st.source}」入库失败：${st.error || "未知错误"}`
            );
          }
        })
        .catch(() => setTimeout(() => pollTask(taskId, itemId), 2000));
    },
    [refreshHealth, showToast]
  );

  // 提交一批文件（每个文件一个异步任务，互不阻塞）
  const submitFiles = useCallback(
    (files: FileList) => {
      const list = Array.from(files);
      if (!list.length) return;
      for (const file of list) {
        const itemId = nextUploadId();
        setUploads((prev) => [
          ...prev,
          { id: itemId, name: file.name, status: "submitting", inserted: 0, error: "" },
        ]);
        submitIngest(file)
          .then(({ task_id }) => {
            setUploads((prev) =>
              prev.map((u) => (u.id === itemId ? { ...u, status: "pending" } : u))
            );
            pollTask(task_id, itemId);
          })
          .catch((e) => {
            setUploads((prev) =>
              prev.map((u) =>
                u.id === itemId
                  ? { ...u, status: "failed", error: (e as Error).message }
                  : u
              )
            );
          });
      }
    },
    [pollTask]
  );

  const handleSend = useCallback(
    async (text: string) => {
      const userMsg: MessageType = { id: nextId(), role: "user", content: text };
      const pendingMsg: MessageType = {
        id: nextId(),
        role: "assistant",
        content: "",
        pending: true,
      };
      setMessages((prev) => [...prev, userMsg, pendingMsg]);

      try {
        const res = await ask(text);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === pendingMsg.id
              ? {
                  ...m,
                  pending: false,
                  content: res.answer,
                  sources: res.sources,
                  rewritten: res.rewritten,
                  hyde: res.hyde,
                }
              : m
          )
        );
      } catch (e) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === pendingMsg.id
              ? { ...m, pending: false, error: (e as Error).message }
              : m
          )
        );
      }
    },
    []
  );

  // ---------- 拖拽上传 ----------

  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    if (e.dataTransfer.files?.length) submitFiles(e.dataTransfer.files);
  };

  return (
    <div
      className="app"
      onDragEnter={onDragEnter}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <div className="aurora" aria-hidden="true" />

      <header className="header">
        <div className="wordmark">
          拾光<span className="dot" />
        </div>
        <span className="status">
          <span className="pulse" />
          {online ? `已连接 · ${rows ?? 0} 片段` : "后端未连接"}
        </span>
        <div className="header-spacer" />
        <ThemeToggle
          theme={theme}
          onToggle={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
        />
      </header>

      <main className="chat" ref={chatRef}>
        {messages.length === 0 ? (
          <div className="empty">
            <div className="eyebrow">BM25 · 语义检索 · RRF 融合</div>
            <h1>问你的知识库</h1>
            <p>上传或拖入文档建立知识库，再用自然语言提问。每一次回答都附上召回来源。</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className="suggestion"
                  onClick={() => handleSend(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => <Message key={m.id} message={m} />)
        )}
      </main>

      {uploads.length > 0 && (
        <div className="uploads">
          {uploads.map((u) => (
            <div key={u.id} className={`upload-item ${u.status}`}>
              <span className="upload-name">{u.name}</span>
              {u.status === "submitting" || u.status === "pending" || u.status === "running" ? (
                <span className="upload-status running">
                  <span className="spinner" />
                  解析中…
                </span>
              ) : u.status === "done" ? (
                <span className="upload-status done">✓ 入库 {u.inserted} 条</span>
              ) : (
                <span className="upload-status failed">✕ {u.error || "失败"}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <Composer onSend={handleSend} onUpload={submitFiles} />

      {toast && <div className="toast">{toast}</div>}
      {dragging && <div className="drop-overlay">松开鼠标，上传文件到知识库</div>}
    </div>
  );
}
