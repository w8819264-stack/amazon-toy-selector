@echo off
chcp 65001 >nul
echo =============================================
echo   GitHub 一键认证 & 推送脚本
echo =============================================
echo.
echo [1/3] 正在打开浏览器进行 GitHub 认证...
echo 请在浏览器中完成授权，然后回到此处。
echo.
"C:\Users\wicor\AppData\Local\gh_cli\bin\gh.exe" auth login --hostname github.com --git-protocol https --web
if %errorlevel% neq 0 (
    echo 认证失败！请重试。
    pause
    exit /b 1
)
echo.
echo [2/3] 认证成功！正在推送代码...
cd /d G:\agent\projects\amazon-toy-selector
git push -u origin main
echo.
echo [3/3] 完成！
pause
