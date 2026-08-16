import { useRef, useState } from "react";

interface Props {
  onSend: (text: string) => void;
  onUpload: (files: FileList) => void;
  uploading: boolean;
}

const ACCEPT =
  ".md,.markdown,.txt,.docx,.pptx,.pdf,.png,.jpg,.jpeg,.bmp,.webp";

export function Composer({ onSend, onUpload, uploading }: Props) {
  const [value, setValue] = useState("");
  const textRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const submit = () => {
    const text = value.trim();
    if (!text) return;
    onSend(text);
    setValue("");
    if (textRef.current) textRef.current.style.height = "auto";
  };

  const autoGrow = () => {
    const el = textRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  };

  return (
    <div className="composer">
      <div className="composer-inner">
        <button
          className="icon-btn"
          onClick={() => fileRef.current?.click()}
          title="上传文档"
          aria-label="上传文档"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21.44 11.05 12.25 20.24a6 6 0 0 1-8.49-8.49l9.2-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
          </svg>
        </button>
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files?.length) onUpload(e.target.files);
            e.target.value = "";
          }}
        />
        <textarea
          ref={textRef}
          rows={1}
          placeholder="问你的知识库…（Enter 发送，Shift+Enter 换行）"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            autoGrow();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          className="send-btn"
          onClick={submit}
          disabled={!value.trim()}
          title="发送"
          aria-label="发送"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      </div>
      {uploading && (
        <div className="uploading">
          <span className="spinner" />
          正在解析并写入知识库…
        </div>
      )}
    </div>
  );
}
