import { useCallback, useEffect, useRef, useState } from "react";
import { ask, deleteFile, health, listFiles, submitIngest, taskDecision, taskStatus } from "./api";
import { Composer } from "./components/Composer";
import { FilesView } from "./components/FilesView";
import { Message } from "./components/Message";
import { ProgressRing } from "./components/ProgressRing";
import { ThemeToggle } from "./components/ThemeToggle";
import type { FileInfo, Message as MessageType, Theme, UploadItem } from "./types";

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
  const [online, setOnline] = useState(false);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [view, setView] = useState<"chat" | "files">("chat");
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [pendingDecision, setPendingDecision] = useState<UploadItem | null>(null);
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
      .then((h) => setOnline(h.milvus_ok))
      .catch(() => setOnline(false));
  }, []);

  // 进入知识库视图时刷新文件列表
  useEffect(() => {
    if (view === "files") refreshFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

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
      .then((h) => setOnline(h.milvus_ok))
      .catch(() => setOnline(false));
  }, []);

  const refreshFiles = useCallback(() => {
    listFiles()
      .then((r) => setFiles(r.files))
      .catch(() => {});
  }, []);

  // 轮询单个入库任务
  const pollTask = useCallback(
    (taskId: string, itemId: string) => {
      taskStatus(taskId)
        .then((st) => {
          if (st.status === "awaiting_decision") {
            // 同名冲突：弹窗等用户决策（一次处理一个）
            setUploads((prev) =>
              prev.map((u) => (u.id === itemId ? { ...u, status: "awaiting_decision" } : u))
            );
            setPendingDecision((prev) =>
              prev ?? {
                id: itemId,
                name: st.source,
                status: "awaiting_decision",
                inserted: 0,
                error: "",
                progress: 0,
                taskId,
              }
            );
            return; // 停止轮询，等决策
          }
          setUploads((prev) =>
            prev.map((u) =>
              u.id === itemId
                ? {
                    ...u,
                    status: st.status,
                    inserted: st.inserted,
                    error: st.error,
                    progress: st.progress ?? 0,
                  }
                : u
            )
          );
          if (st.status === "pending" || st.status === "running") {
            // 状态轮询间隔 30s，避免高频请求压后端（任务进度会稍慢更新）
            setTimeout(() => pollTask(taskId, itemId), 30000);
          } else {
            refreshHealth();
            refreshFiles();
            if (st.status === "done") {
              showToast(`已入库「${st.source}」${st.inserted} 个片段`);
            } else if (st.status === "failed") {
              showToast(`「${st.source}」入库失败：${st.error || "未知错误"}`);
            }
          }
        })
        .catch(() => setTimeout(() => pollTask(taskId, itemId), 30000));
    },
    [refreshHealth, refreshFiles, showToast]
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
          {
            id: itemId,
            name: file.name,
            status: "submitting",
            inserted: 0,
            error: "",
            progress: 0,
          },
        ]);
        submitIngest(file)
          .then(({ task_id }) => {
            setUploads((prev) =>
              prev.map((u) =>
                u.id === itemId ? { ...u, status: "pending", taskId: task_id } : u
              )
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

  // 同名冲突决策
  const decide = useCallback(
    (item: UploadItem, action: "overwrite" | "rename" | "cancel") => {
      if (!item.taskId) return;
      setPendingDecision(null);
      taskDecision(item.taskId, action)
        .then(() => {
          setUploads((prev) =>
            prev.map((u) => (u.id === item.id ? { ...u, status: "running" } : u))
          );
          pollTask(item.taskId!, item.id);
        })
        .catch((e) => {
          setUploads((prev) =>
            prev.map((u) =>
              u.id === item.id
                ? { ...u, status: "failed", error: (e as Error).message }
                : u
            )
          );
        });
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

  const handleDelete = useCallback(
    (docId: string, filename: string) => {
      if (!window.confirm(`确定删除「${filename}」？将同时删除其在知识库中的全部片段。`)) return;
      deleteFile(docId)
        .then(() => {
          refreshFiles();
          refreshHealth();
          showToast(`已删除「${filename}」`);
        })
        .catch((e) => showToast(`删除失败：${(e as Error).message}`));
    },
    [refreshFiles, refreshHealth, showToast]
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

      <aside className="sidebar">
        <div className="sidebar-brand">
          拾光<span className="dot" />
        </div>
        <nav className="sidebar-nav">
          <button
            className={view === "chat" ? "nav-btn active" : "nav-btn"}
            onClick={() => setView("chat")}
          >
            <span className="nav-icon">💬</span>
            问答
          </button>
          <button
            className={view === "files" ? "nav-btn active" : "nav-btn"}
            onClick={() => setView("files")}
          >
            <span className="nav-icon">📁</span>
            知识库
          </button>
        </nav>
      </aside>

      <div className="app-main">
        <header className="header">
          <div className="wordmark">
            拾光<span className="dot" />
          </div>
          <span className="status">
            <span className="pulse" />
            {online ? "已连接" : "后端未连接"}
          </span>
          <div className="header-spacer" />
          <ThemeToggle
            theme={theme}
            onToggle={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
          />
        </header>

        {view === "chat" ? (
          <main className="chat" ref={chatRef}>
            {messages.length === 0 ? (
              <div className="empty">
                <div className="eyebrow">BM25 · 语义检索 · RRF 融合</div>
                <h1>问你的知识库</h1>
                <p>上传或拖入文档建立知识库，再用自然语言提问。每一次回答都附上召回来源。</p>
                <div className="suggestions">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} className="suggestion" onClick={() => handleSend(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => <Message key={m.id} message={m} />)
            )}
          </main>
        ) : (
          <main className="content">
            <FilesView files={files} onRefresh={refreshFiles} onDelete={handleDelete} />
          </main>
        )}

        {uploads.length > 0 && (
          <div className="uploads">
            {uploads.map((u) => (
              <div key={u.id} className={`upload-item ${u.status}`}>
                <span className="upload-name">{u.name}</span>
                {u.status === "submitting" ||
                u.status === "pending" ||
                u.status === "running" ? (
                  <span className="upload-status running">
                    <ProgressRing percent={u.status === "submitting" ? 0 : u.progress ?? 0} size={26} />
                    {u.status === "submitting" ? "上传中…" : `${u.progress ?? 0}%`}
                  </span>
                ) : u.status === "awaiting_decision" ? (
                  <span className="upload-status running">等待处理同名文件…</span>
                ) : u.status === "done" ? (
                  <span className="upload-status done">✓ 入库 {u.inserted} 条</span>
                ) : (
                  <span className="upload-status failed">✕ {u.error || "失败"}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {view === "chat" && <Composer onSend={handleSend} onUpload={submitFiles} />}

        {toast && <div className="toast">{toast}</div>}
      </div>

      {dragging && <div className="drop-overlay">松开鼠标，上传文件到知识库</div>}

      {pendingDecision && (
        <div className="modal-mask">
          <div className="modal">
            <h3>文件名冲突</h3>
            <p>知识库中已有「{pendingDecision.name}」，本次上传如何处理？</p>
            <div className="modal-actions">
              <button className="btn-primary" onClick={() => decide(pendingDecision, "overwrite")}>
                覆盖旧文件
              </button>
              <button className="btn-primary" onClick={() => decide(pendingDecision, "rename")}>
                另存为新文件（加后缀）
              </button>
              <button className="btn-danger" onClick={() => decide(pendingDecision, "cancel")}>
                取消上传
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
