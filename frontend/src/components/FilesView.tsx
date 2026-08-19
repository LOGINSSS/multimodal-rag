import { downloadUrl } from "../api";
import type { FileInfo } from "../types";

interface Props {
  files: FileInfo[];
  onRefresh: () => void;
  onDelete: (docId: string, filename: string) => void;
}

function fmtTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(ts);
  }
}

const STATUS_TEXT: Record<string, string> = {
  done: "已入库",
  ingesting: "入库中",
  failed: "失败",
};

export function FilesView({ files, onRefresh, onDelete }: Props) {
  return (
    <div className="files-view">
      <div className="files-header">
        <h2>知识库文件</h2>
        <button className="text-btn" onClick={onRefresh}>
          刷新
        </button>
      </div>

      {files.length === 0 ? (
        <p className="files-empty">
          还没有文件。去「问答」页上传或拖入文档，入库后会显示在这里。
        </p>
      ) : (
        <table className="files-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th>类型</th>
              <th>片段数</th>
              <th>状态</th>
              <th>上传时间</th>
              <th className="files-actions-col">操作</th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.doc_id}>
                <td className="file-name" title={f.filename}>
                  {f.filename}
                </td>
                <td>{f.doc_type}</td>
                <td>{f.chunk_count}</td>
                <td>
                  <span className={`file-status ${f.status}`}>
                    {STATUS_TEXT[f.status] ?? f.status}
                  </span>
                </td>
                <td>{fmtTime(f.uploaded_at)}</td>
                <td className="files-actions">
                  <a className="link-btn" href={downloadUrl(f.doc_id)} download>
                    下载
                  </a>
                  <button
                    className="danger-btn"
                    onClick={() => onDelete(f.doc_id, f.filename)}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
