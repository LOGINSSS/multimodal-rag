import { useCallback, useEffect, useRef, useState } from "react";
import { ask, health, ingest } from "./api";
import { Composer } from "./components/Composer";
import { Message } from "./components/Message";
import { ThemeToggle } from "./components/ThemeToggle";
import type { Message as MessageType, Theme } from "./types";

const SUGGESTIONS = [
  "这个项目用了哪些模型？",
  "什么是 RRF 混合检索？",
  "总结一下我的知识库",
];

let idCounter = 0;
const nextId = () => `m${++idCounter}`;

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
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const uploadingRef = useRef(false);

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

  const handleUpload = useCallback(
    async (files: FileList) => {
      if (uploadingRef.current) return; // 防重入：一个入库任务进行中时忽略新的上传
      const list = Array.from(files);
      if (!list.length) return;
      uploadingRef.current = true;
      setUploading(true);
      try {
        for (const file of list) {
          const res = await ingest(file);
          showToast(`已入库「${file.name}」${res.inserted} 个片段`);
        }
        const h = await health();
        setRows(h.rows);
        setOnline(h.milvus_ok);
      } catch (e) {
        showToast(`上传失败：${(e as Error).message}`);
      } finally {
        uploadingRef.current = false;
        setUploading(false);
      }
    },
    [showToast]
  );

  return (
    <div className="app">
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
            <p>先上传文档建立知识库，再用自然语言提问。每一次回答都附上召回来源。</p>
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

      <Composer onSend={handleSend} onUpload={handleUpload} uploading={uploading} />

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
