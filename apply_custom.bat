@echo off
REM 在 rustdesk 仓库根目录运行本文件，自动用 custom.json 里的服务器/KEY 应用定制补丁
REM 用法：把本文件、apply_custom.py、custom.json 放到 rustdesk 仓库根目录，双击运行
python "%~dp0apply_custom.py" all --path . --config "%~dp0custom.json"
echo.
echo 已应用补丁，请用 git diff 复查，然后：
echo   flutter pub get
echo   python build.py --flutter --release
pause
