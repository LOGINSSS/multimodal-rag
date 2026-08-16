import type { Message as MessageType } from "../types";

interface Props {
  message: MessageType;
}

export function Message({ message }: Props) {
  if (message.role === "user") {
    return (
      <div className="message user">
        <div className="avatar">你</div>
        <div className="bubble">{message.content}</div>
      </div>
    );
  }

  const hasTrace =
    message.rewritten || message.hyde || (message.sources?.length ?? 0) > 0;

  return (
    <div className="message assistant">
      <div className="avatar">拾</div>
      <div className="bubble">
        {message.pending ? (
          <span className="typing" aria-label="正在思考">
            <span />
            <span />
            <span />
          </span>
        ) : message.error ? (
          <span style={{ color: "var(--danger)" }}>{message.error}</span>
        ) : (
          message.content
        )}

        {!message.pending && hasTrace && (
          <details className="trace">
            <summary>
              <svg
                className="chev"
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
              检索过程
            </summary>
            <div className="trace-body">
              {message.rewritten && (
                <div className="trace-item">
                  <div className="label">改写查询</div>
                  <p>{message.rewritten}</p>
                </div>
              )}
              {message.hyde && (
                <div className="trace-item">
                  <div className="label">HyDE 假设回答</div>
                  <p>{message.hyde}</p>
                </div>
              )}
              {message.sources && message.sources.length > 0 && (
                <div className="trace-item">
                  <div className="label">召回来源</div>
                  {message.sources.map((s, i) => (
                    <p key={i}>
                      <span className="src-name">
                        {s.doc_type || "doc"} · {s.source}
                      </span>
                      <br />
                      {s.text.slice(0, 140)}
                      {s.text.length > 140 ? "…" : ""}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
