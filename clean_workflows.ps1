# 用法：把本脚本放到你的 rustdesk 文件夹根目录，右键“使用 PowerShell 运行”。
# 作用：删除 .github/workflows/ 下所有官方工作流文件（flutter-nightly.yml、flutter.yml、
#       flutter-build.yml、bridge.yml 等），只保留我们自己定制的 build-windows.yml。
# 不会提交，删除后请在 GitHub Desktop 里 Commit 并 Push。

$workflowDir = Join-Path $PSScriptRoot ".github/workflows"
if (-not (Test-Path $workflowDir)) {
    Write-Host "未找到 .github/workflows 文件夹，请确认本脚本放在 rustdesk 仓库根目录。" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

$keep = "build-windows.yml"
$files = Get-ChildItem -Path $workflowDir -Include *.yml, *.yaml -File
$deleted = 0
foreach ($f in $files) {
    if ($f.Name -ne $keep) {
        Remove-Item $f.FullName -Force
        Write-Host ("已删除: " + $f.Name) -ForegroundColor Yellow
        $deleted++
    }
}
Write-Host ("完成。共删除 " + $deleted + " 个官方工作流文件，仅保留 " + $keep + "。") -ForegroundColor Green
Write-Host "接下来请在 GitHub Desktop 里把这次删除 Commit 并 Push。" -ForegroundColor Cyan
Read-Host "按回车退出"
