# 拾光 · RAG 前端

React + Vite + TypeScript。白天蓝白 / 夜晚黑紫双主题，带文件上传的问答界面。

## 启动

```bash
cd frontend
npm install --registry=https://registry.npmmirror.com   # 首次
npm run dev                                              # http://localhost:18080
```

后端先起（`uv run rag serve`），前端通过 `VITE_API_BASE`（默认 `http://127.0.0.1:13080`）连到 FastAPI。

## 结构

```
src/
  App.tsx               # 主界面：主题 / 消息 / 上传 / 健康检查
  main.tsx              # 入口，@fontsource 本地字体
  index.css             # 设计令牌（CSS 变量）＋ 蓝白/黑紫主题 ＋ 极光背景
  api.ts                # /health /ask /ingest 请求封装
  types.ts              # 类型
  components/
    ThemeToggle.tsx     # 太阳↔月亮 变形切换
    Message.tsx         # 气泡 + 检索过程折叠区
    Composer.tsx        # 输入框 + 上传 + 发送
```

## 主题机制

主题由 `<html data-theme="light|dark">` 驱动，全部颜色走 CSS 变量，切换时平滑过渡；
用户选择持久化到 `localStorage`，首次默认跟随系统 `prefers-color-scheme`。

- 白天：蓝白（主色 `#2f6bff`）
- 夜晚：黑紫（主色 `#8b5cf6`）

## 构建

```bash
npm run build   # 产物在 dist/
```
