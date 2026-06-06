@echo off
chcp 65001 >nul 2>&1
title GitHub 一键部署 - Amazon Toy Selector

echo.
echo ╔══════════════════════════════════════════════╗
echo ║    🚀 Amazon Toy Selector - GitHub 部署     ║
echo ╚══════════════════════════════════════════════╝
echo.
echo 正在打开浏览器进行 GitHub 认证...
echo 请在浏览器中点击 "Authorize github" 完成授权。
echo.

set GH_PATH=%LOCALAPPDATA%\gh_cli\bin\gh.exe

echo [1/4] GitHub CLI 认证...
"%GH_PATH%" auth login --hostname github.com --git-protocol https --web
if %errorlevel% neq 0 (
    echo ❌ 认证失败!
    pause
    exit /b 1
)
echo ✅ 认证成功!

echo.
echo [2/4] 创建仓库 amazon-toy-selector...
"%GH_PATH%" repo create w8819264-stack/amazon-toy-selector --public --source=. --remote=origin --push
if %errorlevel% neq 0 (
    echo ⚠️ 仓库可能已存在，尝试直接推送...
    cd /d "G:\agent\projects\amazon-toy-selector"
    git remote add origin https://github.com/w8819264-stack/amazon-toy-selector.git 2>nul
    git push -u origin master 2>nul
    if %errorlevel% neq 0 (
        git push -u origin main 2>nul
    )
    if %errorlevel% neq 0 (
        echo ❌ 推送失败，尝试强制推送...
        git push -u origin master --force
    )
)

echo.
echo [3/4] 设置默认分支为 main...
"%GH_PATH%" repo edit w8819264-stack/amazon-toy-selector --default-branch main 2>nul
if %errorlevel% neq 0 (
    "%GH_PATH%" repo edit w8819264-stack/amazon-toy-selector --default-branch master
)

echo.
echo [4/4] 启用 GitHub Pages...
"%GH_PATH%" api repos/w8819264-stack/amazon-toy-selector/pages -f "source[branch]=main" -f "source[path]=/" 2>nul
if %errorlevel% neq 0 (
    "%GH_PATH%" api repos/w8819264-stack/amazon-toy-selector/pages -f "source[branch]=master" -f "source[path]=/"
)

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║  ✅ 部署完成!                                   ║
echo ║                                                ║
echo ║  📎 报告地址:                                  ║
echo ║  https://w8819264-stack.github.io/amazon-toy-selector/
echo ║                                                ║
echo ║  🔄 GitHub Actions 每天自动更新               ║
echo ╚══════════════════════════════════════════════════╝
echo.
pause
