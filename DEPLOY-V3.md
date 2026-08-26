# v3 修复版部署指南（这次改了什么 + 你要做什么）

## 一句话总结

之前失败的原因找到了 **3 个**，都已修复。你现在只需要
**把 1 个文件（build-windows.yml）换成新版**，再重新跑一次即可。

---

## 之前为什么一直失败（大白话）

| # | 问题 | 大白话解释 |
|---|------|-----------|
| 1 | vcpkg 版本过期 | RustDesk 依赖一批「现成的零件库」。官方最近升级了零件库的版本号，而我之前把旧版本号**写死**在构建文件里。两边对不上号，GitHub 刚开始装零件就报错退出了。**新版会自动读取仓库里的正确版本号，永远不会再对不上。** |
| 2 | 缺了官方必做步骤 | RustDesk 在 Windows 上编译时，必须先把 Flutter 的「引擎」换成 RustDesk 自己魔改过的版本，还要打一个小补丁。我之前漏了这两步，所以就算零件装好了，最后编译也会失败。**新版已补上这两个官方步骤。** |
| 3 | 编译参数不全 | 我之前给编译命令的参数不完整。**新版完全照抄官方的完整参数。** |

> 简单说：这次的 v3 版构建文件，是**逐行对照 RustDesk 官方自己的构建流程**改出来的，
> 官方怎么编，我们就怎么编，只多加了「内置你的服务器和 KEY + 精简界面」这一步。

---

## 你要做的（只需换 1 个文件）

### 第 1 步：把新文件放进你的 rustdesk 文件夹

1. 下载并解压 `rustdesk-custom-win.zip`。
2. 打开解压出的 `fork-root\.github\workflows\` 文件夹，里面有 1 个文件：`build-windows.yml`。
3. 把它**复制**到你电脑上的 rustdesk 文件夹（GitHub Desktop 里 `Repository → Show in Explorer` 打开的那个），
   放进 `.github\workflows\` 里，**覆盖旧的**同名文件。
   （文件管理器要先勾「查看 → 隐藏的项目」才能看到 `.github` 文件夹。）
4. 打开 GitHub Desktop → 左边会显示 1 个文件被修改 → 底部 Summary 随便写 `v3` →
   点 **Commit to main** → 再点 **Push origin**。

**怎么确认换对了？** 在 GitHub 网页打开你仓库里的
`.github/workflows/build-windows.yml`，最上面几行有 `v3（2026-08-26 大修版）`字样，就是新版。

> 不想用 GitHub Desktop 也可以：在 GitHub 网页打开该文件 → 点铅笔 ✏️ → 全选删掉 →
> 把 zip 里新文件的完整内容粘贴进去 → 底点 Commit changes。效果一样。

### 第 2 步：跑一次全新的构建

1. 打开你的仓库网页 → 顶部 **Actions**。
2. 左边选 **Build Custom RustDesk (Windows)**。
3. 点右上角绿色 **Run workflow → Run workflow**。
   （⚠️ 一定要点绿色按钮跑**新的**，不要在旧记录上点 Re-run——那会用旧文件重跑，白等。）

### 第 3 步：等 + 下载

- 全程约 **1.5～2 小时**（为了稳定我们没有用缓存，会慢一些，属正常）。
- 跑完出现绿色对勾 ✔ → 点进这次运行 → 页面下方 **Artifacts → rustdesk-windows** → 下载。
- 解压后就是自带你服务器（183.87.130.6）和 KEY、界面已精简的 RustDesk 客户端，
  整个文件夹拷到任何 Windows 电脑，双击 `rustdesk.exe` 就能用。

---

## 万一又失败了：怎么把真正的报错发给我（重要！）

GitHub 首页那个 Annotations 框只显示「警告」，**真正的报错藏在标红步骤的日志里**。
按下面的方法取（30 秒）：

1. 打开仓库 → **Actions** → 点最新那条失败的记录（红色 ×）。
2. 页面左边（或展开 build-windows 后）有一串步骤，找到**左边带红色 ×** 的那一步，点它。
3. 右边日志自动展开，**拖到最底部**。
4. 把**最后 20~30 行**（尤其是红色字）复制出来发我，并告诉我**这一步的名字**。

步骤名字对照（看到哪个红了就说哪个）：
`Read vcpkg baseline` / `Setup vcpkg` / `Install vcpkg dependencies` /
`Replace engine` / `Patch flutter` / `Apply custom patch` /
`Install flutter_rust_bridge codegen` / `flutter pub get + generate bridge` /
`Build rustdesk (Windows x64)` / `Upload artifact`

> 提示：`Install vcpkg dependencies` 这一步如果失败，新版会**自动把详细日志打印出来**，
> 你直接把最后一大段发我即可。

---

## 顺便说一句

- 那 1 条 `Node.js 20 is deprecated` 警告是 GitHub 自己的提示，**无害，永远不用管**。
- `Install vcpkg dependencies` 要装几十个零件，**跑 30~50 分钟很正常**，别中途取消。
- 成功后如果想要更多界面精简（比如隐藏「安全」「账号」页签），把 zip 里的
  `RustDesk.toml` 和 `rustdesk.exe` 放同一目录即可（新构建已自动放进产物里）。
