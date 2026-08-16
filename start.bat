@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title 拾光 RAG 一键启动

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "MILVUS_PORT=19530"
set "BACKEND_PORT=13080"
set "FRONTEND_PORT=18080"

echo.
echo  ======================================================
echo    拾光 RAG 一键启动
echo    后端 :%BACKEND_PORT%    前端 :%FRONTEND_PORT%    Milvus :%MILVUS_PORT%
echo  ======================================================
echo.

REM ---------------- 1. 前置环境检查 ----------------
where uv >nul 2>&1
if errorlevel 1 (
    echo  [X] 未找到 uv，请先安装 https://docs.astral.sh/uv/
    goto :fail
)
where node >nul 2>&1
if errorlevel 1 (
    echo  [X] 未找到 node，请先安装 Node.js
    goto :fail
)
if not exist ".env" (
    echo  [!] 未找到 .env，已从 .env.example 复制（请填入 API key）
    copy /y ".env.example" ".env" >nul
)
echo  [1/5] 环境检查通过 (uv / node / .env)

REM ---------------- 2. Docker ----------------
echo  [2/5] 检查 Docker...
docker info >nul 2>&1
if errorlevel 1 (
    echo  [!] Docker 未运行，尝试启动 Docker Desktop...
    call :startDocker
    if errorlevel 1 (
        echo  [X] Docker 启动失败，请手动打开 Docker Desktop 后重试
        goto :fail
    )
)
echo  [OK] Docker 就绪

REM ---------------- 3. Milvus ----------------
echo  [3/5] 启动 Milvus (docker compose up -d)...
docker compose up -d
call :waitPort %MILVUS_PORT% 60
if errorlevel 1 (
    echo  [X] Milvus 端口 %MILVUS_PORT% 未就绪，请检查 docker compose ps
    goto :fail
)
echo  [OK] Milvus 已就绪

REM ---------------- 4. 端口清理（旧服务） ----------------
echo  [4/5] 检查并清理旧服务端口...
call :freePort %BACKEND_PORT%
call :freePort %FRONTEND_PORT%

REM ---------------- 5. 打开两个终端窗口 ----------------
echo  [5/5] 启动前后端...
start "RAG 后端" /D "%ROOT%" cmd /k "uv run rag serve"
start "RAG 前端" /D "%ROOT%frontend" cmd /k "npm run dev"

echo.
echo  ======================================================
echo    启动完成
echo    后端 API : http://127.0.0.1:%BACKEND_PORT%/docs
echo    前端     : http://localhost:%FRONTEND_PORT%
echo    关闭     : 直接关掉两个窗口即可
echo  ======================================================
echo.
timeout /t 4 >nul
exit /b 0

:fail
echo.
echo  [X] 启动中止，请按上方提示处理后重新运行。
echo.
pause
exit /b 1

REM ===================== 函数 =====================

:startDocker
set "DD=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if exist "%DD%" (
    start "" "%DD%"
) else (
    set "DD=%LocalAppData%\Docker\Docker Desktop.exe"
    if exist "!DD!" start "" "!DD!"
)
set /a "n=0"
:dockerWait
docker info >nul 2>&1
if not errorlevel 1 exit /b 0
set /a "n+=1"
if !n! geq 90 exit /b 1
timeout /t 1 >nul
goto :dockerWait

:waitPort
set "port=%~1"
set "secs=%~2"
set /a "n=0"
:waitPortLoop
netstat -ano | findstr /i LISTENING | findstr /c:":!port! " >nul 2>&1
if not errorlevel 1 exit /b 0
set /a "n+=1"
if !n! geq !secs! exit /b 1
timeout /t 1 >nul
goto :waitPortLoop

:freePort
set "port=%~1"
set "killed="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /i LISTENING ^| findstr /c:":!port! "') do (
    set "killed=1"
    echo  [*] 端口 !port! 被 PID %%a 占用，正在结束...
    taskkill /f /pid %%a >nul 2>&1
)
if defined killed (
    timeout /t 2 >nul
) else (
    echo  [OK] 端口 !port! 空闲
)
exit /b 0
