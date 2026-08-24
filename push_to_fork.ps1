# ==========================================================================
# 一键推送到你的 rustdesk fork 并打 tag 触发构建
# --------------------------------------------------------------------------
# 用法（在你本机的 rustdesk fork 根目录里，先把这些文件复制进去后运行）：
#   .\push_to_fork.ps1 -RemoteUrl https://github.com/你的名/rustdesk.git
#   （也可不传 -RemoteUrl，脚本会直接用已有的 origin）
#
# 前置：本机已装 git，且已 Fork 好 rustdesk/rustdesk。
# 说明：脚本只负责 git 提交/打 tag/推送；构建由 GitHub Actions 完成。
# ==========================================================================
param(
    [string]$RemoteUrl = ""
)

if (-not (Test-Path .git)) {
    Write-Error "当前目录不是 git 仓库。请先 `git clone` 你的 fork，再在里面运行本脚本。"
    exit 1
}

# 若提供了 RemoteUrl 且 origin 不存在，则添加
if ($RemoteUrl -ne "") {
    $hasOrigin = git remote get-url origin 2>$null
    if ($LASTEXITCODE -ne 0) {
        git remote add origin $RemoteUrl
        Write-Host "已添加 remote origin -> $RemoteUrl"
    } else {
        Write-Host "origin 已存在 -> $hasOrigin（忽略 -RemoteUrl）"
    }
}

# 仅添加本工具包相关文件，避免误提交其它改动
$files = @(
    "apply_custom.py",
    "custom.json",
    "RustDesk.toml",
    "apply_custom.bat",
    "README-Windows.md",
    ".github/workflows/build-windows.yml"
)
foreach ($f in $files) {
    if (-not (Test-Path $f)) {
        Write-Warning "找不到文件: $f （请确认已把 fork-root 内容复制到仓库根目录）"
    }
}

git add $files
git commit -m "custom windows client: built-in server+key, trimmed UI" 2>&1 | Write-Host

# 打 tag 触发 Actions（也可到 Actions 页手动 Run）
$tag = "v1custom"
git tag -a $tag -m "custom windows client" 2>&1 | Write-Host

Write-Host ""
Write-Host "正在推送到 origin 并推送 tag（会触发 GitHub Actions 构建）..."
git push origin HEAD 2>&1 | Write-Host
git push origin --tags 2>&1 | Write-Host

Write-Host ""
Write-Host "完成。请到 GitHub -> Actions -> Build Custom RustDesk (Windows) 查看构建进度，"
Write-Host "跑完后到 Artifacts 下载 rustdesk-windows 即可。"
