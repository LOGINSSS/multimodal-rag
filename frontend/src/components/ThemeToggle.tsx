import type { Theme } from "../types";

interface Props {
  theme: Theme;
  onToggle: () => void;
}

// 太阳 ↔ 月亮 变形切换（交叉淡入 + 旋转）
export function ThemeToggle({ theme, onToggle }: Props) {
  const label = theme === "light" ? "切换到夜晚" : "切换到白天";
  return (
    <button
      className="theme-toggle"
      onClick={onToggle}
      title={label}
      aria-label={label}
      aria-pressed={theme === "dark"}
    >
      <span className="icon icon-sun" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="4" />
          <path
            strokeLinecap="round"
            d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
          />
        </svg>
      </span>
      <span className="icon icon-moon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"
          />
        </svg>
      </span>
    </button>
  );
}
