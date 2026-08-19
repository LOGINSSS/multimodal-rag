interface Props {
  percent: number;
  size?: number;
}

/** 环形进度圈，中心显示百分比。 */
export function ProgressRing({ percent, size = 30 }: Props) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(100, percent));
  const offset = c * (1 - p / 100);
  return (
    <svg
      className="progress-ring"
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="progressbar"
      aria-valuenow={p}
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        className="progress-ring-bg"
        fill="none"
        strokeWidth={4}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        className="progress-ring-fg"
        fill="none"
        strokeWidth={4}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
      />
      <text
        x="50%"
        y="50%"
        textAnchor="middle"
        dominantBaseline="central"
        className="progress-ring-text"
      >
        {p}%
      </text>
    </svg>
  );
}
