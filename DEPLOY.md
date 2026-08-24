# 小白一步步部署指南（Windows 自定义 RustDesk 客户端）

你不用写任何命令。本指南用「GitHub 网站 + GitHub Desktop 图形界面」完成，
全程点鼠标，**不需要懂命令行，也不需要配置 Secrets**（服务器和 KEY 已经写进 `custom.json` 了）。

---

## 先弄懂三个词（很重要）

- **GitHub**：一个存放代码网站的网站（github.com）。RustDesk 的源代码就放在这里。
- **Fork（复刻）**：把别人（rustdesk 官方）的项目，**复制一份到你自己的账号下**。
  你只能改自己账号下的副本，改完也不会影响官方。
- **Clone（克隆）**：把你账号下「网上的项目」**下载到你电脑的一个文件夹里**，
  这样你才能在电脑上往里放文件。

一句话流程：**Fork（网上复制一份）→ Clone（下载到电脑）→ 把我的文件放进去 → 推回网上 → 让 GitHub 自动编译**。

---

## 第 1 步：注册 GitHub 账号
1. 打开 https://github.com ，点右上角 **Sign up**，用邮箱注册一个账号。
2. 注册完登录。

## 第 2 步：Fork（复刻）RustDesk 官方仓库
1. 在浏览器打开：https://github.com/rustdesk/rustdesk
2. 点页面右上角的 **Fork** 按钮（挨着 Star / Watch）。
3. 弹出页面直接点 **Create fork**（不用改任何选项）。
4. 几秒后，你会跳到 `github.com/你的用户名/rustdesk` —— 这就是**你自己的副本**。

## 第 3 步：安装 GitHub Desktop（图形界面，免敲命令）
1. 打开 https://desktop.github.com/ ，下载并安装 **GitHub Desktop**。
2. 打开它，用第 1 步注册的账号登录。

## 第 4 步：Clone（克隆）你 fork 的项目到电脑
1. 在 GitHub Desktop 里：左上角 **File → Clone repository…**
2. 切到 **GitHub.com** 标签，找到 `你的用户名/rustdesk`，选中它，点 **Clone**。
3. 它会问保存到哪个文件夹，用默认即可。点完，**你电脑上就有了一个 rustdesk 文件夹**。
   （这一步就是「Clone / 克隆」——把网上的项目下载到本地。）

## 第 5 步：把我的文件放进去
1. 下载我给你的 **`rustdesk-custom-win.zip`**，解压，得到 `fork-root` 文件夹。
2. 打开 `fork-root` 文件夹，把里面**所有内容**复制。
3. 粘贴到你第 4 步克隆出来的 **rustdesk 文件夹**里（和里面的 README.md 等文件放一起）。
   - 重点是那个 `.github` 文件夹也要一起复制进去（它里面藏着自动编译的指令）。
   - 如果提示「有同名文件」，选**替换/合并**即可（不会破坏编译需要的文件）。

## 第 6 步：提交并推送到网上
1. 回到 **GitHub Desktop**，它会自动发现你新增/修改的文件（左边会列出一堆文件）。
2. 左下角 **Summary（必填）** 随便写，例如：`添加自定义构建配置`。
3. 点 **Commit to main**（提交到本地）。
4. 再点右上角的 **Push origin**（推送到网上）。
5. 等几秒，文件就上传到你 GitHub 上的 fork 了。

## 第 7 步：让 GitHub 自动编译（不需要你装任何编译环境）
1. 在浏览器打开 `github.com/你的用户名/rustdesk`。
2. 点仓库顶部的 **Actions** 标签。
3. 左边列表里找到 **Build Custom RustDesk (Windows)**，点它。
4. 如果看到黄色提示「workflows can't run」之类，先点 **I understand…** 同意一下。
5. 点右边的 **Run workflow → Run workflow** 按钮启动。
   （如果你在第 6 步推送时它已经自动开始跑了，就跳过这步。）
6. 页面会出现一个运行记录，点进去可以看到实时日志。
   **编译大约需要 40~70 分钟**，请耐心等（这是 GitHub 的免费电脑在帮你编）。

## 第 8 步：下载成品
1. 编译跑完（绿色对勾）后，在刚才的运行记录页面往下拉，找到 **Artifacts** 区域。
2. 点 **rustdesk-windows** 下载（是个 zip）。
3. 解压后里面的 `rustdesk.exe` 就是**自带你的服务器和 KEY、界面已精简**的客户端了。
4. 把它发给需要用的人，双击即可使用。

---

## 常见问题
- **要不要配 Secrets？** 不用。服务器和 KEY 已写进 `custom.json`，工作流会自动读它。
- **Actions 里找不到 "Build Custom RustDesk (Windows)"？**
  说明第 5 步的 `.github/workflows/build-windows.yml` 没复制进去，回去检查一下。
- **编译报错了？** 把 Actions 里的红色报错文字发给我，我帮你改工作流。
- **想换服务器地址 / KEY？** 改 `custom.json` 里的两行，重新走第 6~8 步即可。

## 一次性前置（一般默认就满足，不用管）
仓库 `Settings → Actions → General` 里：
- `Allow all actions and reusable workflows` 勾上
- `Workflow permissions` 设为 `Read and write permissions`
（如果构建时提示没权限，再来这里改。）
