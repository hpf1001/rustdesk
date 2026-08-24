# RustDesk 自定义 Windows 客户端（内置服务器 + KEY + 精简界面）

本工具包帮你把自建 RustDesk 服务器地址和公钥 **烧进客户端**，并 **精简界面**
（隐藏“设置-网络”页签和主界面“ID/中继服务器”输入框），最终产出 Windows 的 `.exe`。

> 本环境无法直接编译 Windows 二进制，下方两种方式都基于 **你的 GitHub 仓库 + Actions**，
> 或你本机装好 Flutter 后本地编译。工具包只负责“改源码”，构建仍由官方流程完成。

---

## 一、你需要准备的信息
1. **hbbs 地址**：你自建 ID/中继服务器域名或 IP，带端口，例如 `rustdesk.example.com:21116`
   （中继 hbbr 默认同机 `:21117`，hbbs 会自动下发给客户端，一般无需单独配）。
2. **公钥 KEY**：部署 hbbs 后生成的 `id_ed25519.pub` 文件全文（一长串 Base64）。
   - 不知道在哪？登录服务器执行 `cat ~/.rustdesk-server/id_ed25519.pub` 或到 hbbs 数据目录查找。

---

## 二、方式 A：GitHub Actions 在线编译（推荐，无需本机装环境）

本工具包的 `build-windows.yml` 是**自包含、单平台（Windows x64）** 工作流：
它自己完成「检出子模块 → 装 Rust/Flutter/LLVM/vcpkg → 生成 flutter_rust_bridge 代码 → 应用补丁 → 编译 → 上传产物」，
**不需要**复制官方 `flutter-build.yml` / `bridge.yml`，也不需单独 fork `hbb_common`。

### 步骤
1. 在 GitHub 上 **Fork** `rustdesk/rustdesk` 到你的账号（得到 `你的名/rustdesk`）。
2. 把本工具包里的以下 4 个文件提交进你的 fork 根目录：
   - `apply_custom.py`        （补丁脚本，工作流会调用它）
   - `custom.json`            （含你的服务器/KEY，脚本自动读取；也可改用 Secrets）
   - `RustDesk.toml`          （编译后随包附带，进一步隐藏设置项）
   - `build-windows.yml`      → 放到 `.github/workflows/build-windows.yml`
3. 仓库 → `Settings → Secrets and variables → Actions → New repository secret`：
   - `RENDEZVOUS_SERVER` = `183.87.130.6:21116`
   - `RS_PUB_KEY` = `whc2k1hiKsRdtkh1L59n1Cwbu0LVOOIez96Sr+VEA+o=`
   （Secrets 优先级高于 `custom.json`；两者留其一即可）
4. 仓库 → `Settings → Actions → General`：勾选
   `Allow all actions and reusable workflows`，并把 `Workflow permissions` 设为 `Read and write permissions`。
5. 打 tag 触发构建：
   ```bash
   git tag -a v1custom -m "custom windows client"
   git push --tags
   ```
   或到 `Actions → Build Custom RustDesk (Windows) → Run workflow` 手动触发。
6. 跑完后到 `Actions` 运行记录的 **Artifacts** 下载 `rustdesk-windows`，解压后 `rustdesk.exe`
   就是自带服务器/KEY、且已隐藏“设置-网络”和“ID/中继服务器输入框”的客户端。

> 说明：工作流里 `RustDesk.toml` 会被自动复制到产物目录（`rustdesk.exe` 同目录），
> 用于隐藏“安全/账号/检查更新”等入口；若不想附带可删掉工作流里「Bundle RustDesk.toml」那一步。
> 另外，`RustDeskTempTopMostWindow`（置顶小窗）和打印机驱动为可选功能，本工作流未打包它们，不影响主功能。

> 编译若因 `--hwcodec`（硬件编解码）失败，可在 `build-windows.yml` 的 Build 步骤去掉 `--hwcodec --vram`，
> 改为 `python build.py --flutter` 重试；功能不受影响，只是少了硬件加速。

---

## 三、方式 B：本机 Windows 编译（已装 Flutter 环境时）

前置：Rust (stable)、Flutter (stable)、Visual Studio“C++ 桌面开发”、
LLVM(加入 PATH)、vcpkg(`libvpx/libyuv/opus/aom` 的 `x64-windows-static`) + 配置 `VCPKG_ROOT`。

```powershell
git clone https://github.com/你的名/rustdesk
cd rustdesk
# 应用定制补丁（写服务器/KEY + 精简界面）
python apply_custom.py all --path . --server "rustdesk.example.com:21116" --key "你的公钥"
# 复查改动
git diff
# 编译
flutter pub get
python build.py --flutter --release
```
产物在 `build\windows\x64\runner\Release\`（含 `rustdesk.exe`、数据目录等）。

---

## 四、补丁做了什么（可 `git diff` 复查）

| 文件 | 改动 | 作用 |
|------|------|------|
| `libs/hbb_common/src/config.rs` | `RENDEZVOUS_SERVERS` = 你的服务器 | **内置 ID/中继服务器地址** |
| `libs/hbb_common/src/config.rs` | `RS_PUB_KEY` = 你的公钥 | **内置 KEY** |
| `src/client.rs` | `get_rs_pk(...)` 始终用 `config::RS_PUB_KEY` | **锁死 KEY**，忽略用户填写 |
| `flutter/.../desktop_setting_page.dart` | 注释整个包裹 `SettingsTabKey.network` 的 `if` 块 | 隐藏“设置-网络”页签（防编译报错） |
| `flutter/.../connection_page.dart` | `setupServerWidget` 的 `offstage: true` | 隐藏主界面“ID/中继服务器”输入框 |

> 说明：当前 master 中 `RS_PUB_KEY` 本就是“key 为空时的回退值”，因此只要改它即可内置；
> 额外锁死 `client.rs` 是为了连用户在配置文件里手填的 key 也一并忽略，防止白嫖/绕回官方服务器。

---

## 五、常见问题
- **hbb_common 必须能被 Actions 拉到**：本方案直接在 `libs/hbb_common` 子模块的工作树里改文件再编译，
  **不需要**单独 fork hbb_common，最简单。
- **中继连不上？** 确认 hbbr 在 `:21117` 已启动；多数情况下 hbbs 会自动下发中继地址。
- **想连回官方服务器？** 已锁死 KEY + 隐藏入口，普通用户改不了；如你要调试可临时改回 `client.rs`。
- **升级提示仍在？** 设置了自定义服务器后 `isCustomClient()` 为 true，官方升级卡片会自动隐藏；
  另可用 `RustDesk.toml` 里的 `enable-check-update = "N"` 双保险。
