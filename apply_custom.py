#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RustDesk Windows 定制补丁脚本 v3.7（跨平台，Python 3.8+）
=====================================================
作用：
  1. 把自建 ID/中继服务器地址和公钥 KEY 烧进源码（hbb_common/src/config.rs）
  2. 锁死 KEY，使客户端不使用用户在“设置-网络”里填写的 key（始终用内置 RS_PUB_KEY）
  3. 让 custom.txt 的预设真正生效（修补 hbb_common 的 get_or，把 HARD_SETTINGS
     作为「预设」插在 LOCAL 与 DEFAULT 之间；v3.7 起 custom.txt 无签名纯 JSON
     可被解析，取代从未被读取的 RustDesk.toml）
  4. 精简界面：
       - 隐藏“设置”里的 网络/安全/账户/打印机 四个页签
       - 隐藏主界面上的“ID/中继服务器”输入框
       - 主页面只保留“你的桌面”(标题+简介+ID+固定密码面板) 与右侧“控制远程桌面”
       - 隐藏“控制远程桌面”下方 5 个浏览标签页（最近/收藏/已发现/地址簿/可访问的设备）
  5. v3.7 修复【固定密码失效 + 退出远程后自动锁屏】：
       - 根源一（固定密码）：RustDesk 自定义客户端配置只有一条官方加载路径——
         exe 同目录的 custom.txt（base64 + RustDesk 官方私钥签名，我们无法伪造）。
         之前各版本附带的 RustDesk.toml 客户端【从来不读】（全源码无读取代码），
         所以 v3.3 起预设的固定密码/行为选项从未生效——新电脑上没有本地永久
         密码，就只剩一次性密码可连。
       - 修复一：给 src/common.rs 的 read_custom_client() 打补丁——签名校验
         失败时回退按「无签名纯 JSON」解析。再随产物附带一份纯 JSON 的
         custom.txt（含 password/salt 预设密码与 override-settings 行为选项，
         放在 exe 同目录），固定密码即可生效（1.3.9 与 master 该函数逐字一致，
         一个正则通吃）。
       - 根源二（自动锁屏）：“会话结束后锁定”是【控制端】通过 OptionMessage
         下发给被控端的（被控端 src/server/connection.rs 默认 false、收到
         Yes 才锁）。控制端勾选/默认值置 Y 后，每台被控机退出即锁屏。
       - 修复二：被控端补丁——忽略控制端下发的 lock_after_session_end，
         任何情况下退出远程都不锁屏（1.3.9 路径 src/connection.rs 与
         master 路径 src/server/connection.rs 均覆盖，存在哪个打哪个）。
  6. v3.6 修复【关闭窗口后被控断联】+【开机自启常驻待机】（保留）：
       - 根源：便携版的被控服务(server)原本跑在【主界面进程内的一个线程】里，
         主界面一退出它就跟着死；而托盘是独立进程、图标还挂着——于是出现
         “图标在、看着服务已启动、实际早已断联”的假象。
       - 修复：被控服务改由【托盘进程】承载（托盘进程永不退出）：
         · 主界面随便关、甚至进程结束，被控在线不受影响；
         · 托盘进程启动时自动把自己注册进“开机自启”（注册表 Run 键，
           参数 --tray：开机静默进入右下角待机，不弹主窗口）；
         · 点托盘图标即可重新打开主界面。
  7. v3.5 两项修复保留：
       - 【托盘图标】无参数启动主程序时无条件确保托盘进程在运行（独立 --tray 进程）。
       - 【标签页】结构匹配 + 从布局中直接移除，双保险。
  8. v3.5 起的【补丁后强制校验】：任何一个关键补丁没打上，脚本立刻报错退出，
     让 GitHub Actions 构建当场失败并显示原因——绝不再出现
     「正则静默失配 → 白等 2 小时构建出未修复版本」的情况。
  9. v3.4 已验证有效的修复全部保留：
       - 主窗口关闭 → 隐藏到托盘（onWindowClose），服务常驻
       - 被控端无感：强制隐藏“连接管理/连接状态”窗口

用法（在 rustdesk 仓库根目录运行）：
  python apply_custom.py all --path . --server "rustdesk.example.com:21116" --key "你的公钥"
  python apply_custom.py hbb      --path libs/hbb_common --server "..." --key "..."
  python apply_custom.py rustdesk --path .
  python apply_custom.py selftest        # 用内置样例验证正则是否匹配当前源码结构

说明：
  --path 对 all / rustdesk 指向 rustdesk 仓库根；对 hbb 指向 hbb_common 仓库根。
  不指定 --server/--key 时仅做界面精简，不写服务器/KEY（可用占位后补）。
  加 --dry-run 只打印将要改动、不写文件（此时跳过强制校验）。
"""
import os
import re
import sys
import io
import argparse
import tempfile
import shutil

# ---- 关键：强制把 stdout/stderr 设成 UTF-8，避免 Windows cp1252 控制台打印中文崩溃 ----
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def patch_file(path, edits, dry=False, verbose=True):
    """edits: list of (compiled_regex, replacement)"""
    if not os.path.exists(path):
        if verbose:
            print(f"  [SKIP] 文件不存在: {path}")
        return False
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    original = text
    for rx, repl in edits:
        text, n = rx.subn(repl, text)
        if n and verbose:
            print(f"  [PATCH] {os.path.relpath(path)}  ({n} 处)")
    if text != original:
        if not dry:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        elif verbose:
            print(f"  [DRY-RUN] 将对 {os.path.relpath(path)} 写入改动")
        return True
    if verbose:
        print(f"  [NOCHANGE] {os.path.relpath(path)}")
    return False


# ---------- hbb_common/src/config.rs ----------
def patch_hbb(root, server, key, dry=False):
    print("==> 处理 hbb_common (config.rs)")
    p = os.path.join(root, "src", "config.rs")
    edits = []
    # 3) 让 RustDesk.toml 的 [options] 预设真正生效。
    #    get_or 原解析链为 OVERWRITE -> LOCAL -> DEFAULT，完全不含 HARD_SETTINGS，
    #    导致 verification-method / approve-mode / access-mode / direct-server 等
    #    被 get_option 读取的「行为选项」对全新客户端无效（toml 写了也不生效）。
    #    把 HARD_SETTINGS 作为「预设」插在 LOCAL 与 DEFAULT 之间：
    #       - toml 预设可覆盖代码默认值（满足定制需求）
    #       - 用户本地配置 (LOCAL) 仍优先于 toml 预设（语义正确）
    edits.append((
        re.compile(r"\.or\(c\.read\(\)\.unwrap\(\)\.get\(k\)\)"),
        ".or(HARD_SETTINGS.read().unwrap().get(k))\n        .or(c.read().unwrap().get(k))",
    ))
    if server:
        edits.append((
            re.compile(r'pub const RENDEZVOUS_SERVERS: &\[&str\] = &\[[^\]]*\];'),
            f'pub const RENDEZVOUS_SERVERS: &[&str] = &["{server}"];',
        ))
    if key:
        edits.append((
            re.compile(r'pub const RS_PUB_KEY: &str = "[^"]*";'),
            f'pub const RS_PUB_KEY: &str = "{key}";',
        ))
    patch_file(p, edits, dry)


# ---------- v3.7 P1：custom.txt 无签名纯 JSON 回退（src/common.rs） ----------
# read_custom_client 原逻辑：decode64 -> 官方公钥验签 -> JSON 解析。
# 签名私钥在 RustDesk 官方手里，自建客户端永远过不了验签 -> custom.txt 形同虚设。
# 补丁：验签失败时回退把输入当纯 JSON 解析（1.3.9 与 master 此段逐字一致）。
# 配套：仓库根放一份纯 JSON custom.txt，工作流把它复制到 exe 同目录。
READ_CUSTOM_RE = re.compile(
    r'pub fn read_custom_client\(config: &str\) \{\s*\n'
    r'\s*let Ok\(data\) = decode64\(config\) else \{\s*\n'
    r'\s*log::error!\("Failed to decode custom client config"\);\s*\n'
    r'\s*return;\s*\n\s*\};\s*\n'
    r'\s*const KEY: &str = "5Qbwsde3unUcJBtrx9ZkvUmwFNoExHzpryHuPUdqlWM=";\s*\n'
    r'\s*let Some\(pk\) = get_rs_pk\(KEY\) else \{\s*\n'
    r'\s*log::error!\("Failed to parse public key of custom client"\);\s*\n'
    r'\s*return;\s*\n\s*\};\s*\n'
    r'\s*let Ok\(data\) = sign::verify\(&data, &pk\) else \{\s*\n'
    r'\s*log::error!\("Failed to dec custom client config"\);\s*\n'
    r'\s*return;\s*\n\s*\};\s*\n'
    r'\s*let Ok\(mut data\) =\s*\n'
    r'\s*serde_json::from_slice::<std::collections::HashMap<String, serde_json::Value>>\(&data\)\s*\n'
    r'\s*else \{\s*\n'
    r'\s*log::error!\("Failed to parse custom client config"\);\s*\n'
    r'\s*return;\s*\n\s*\};'
)
READ_CUSTOM_REPL = (
    'pub fn read_custom_client(config: &str) {\n'
    '    // [custom build] v3.7: official custom.txt must be signed with\n'
    '    // RustDesk\'s private key, which self-hosted builds cannot produce.\n'
    '    // Try the signed path first; if it fails, fall back to parsing the\n'
    '    // input as plain JSON so unsigned custom.txt presets (password/salt,\n'
    '    // override-settings) take effect.\n'
    '    let mut parsed: Option<std::collections::HashMap<String, serde_json::Value>> = None;\n'
    '    if let Ok(encoded) = decode64(config) {\n'
    '        const KEY: &str = "5Qbwsde3unUcJBtrx9ZkvUmwFNoExHzpryHuPUdqlWM=";\n'
    '        if let Some(pk) = get_rs_pk(KEY) {\n'
    '            if let Ok(verified) = sign::verify(&encoded, &pk) {\n'
    '                parsed = serde_json::from_slice(&verified).ok();\n'
    '            }\n'
    '        }\n'
    '    }\n'
    '    if parsed.is_none() {\n'
    '        parsed = serde_json::from_str(config).ok();\n'
    '    }\n'
    '    let Some(mut data) = parsed else {\n'
    '        log::error!("Failed to parse custom client config");\n'
    '        return;\n'
    '    };'
)


def patch_common(root, dry=False):
    print("==> v3.7 P1: custom.txt 无签名纯 JSON 回退 (src/common.rs)")
    p = os.path.join(root, "src", "common.rs")
    patch_file(p, [(READ_CUSTOM_RE, lambda m: READ_CUSTOM_REPL)], dry)


# ---------- v3.7 P2：被控端忽略“退出后锁屏”（connection.rs） ----------
# lock_after_session_end 由控制端通过 OptionMessage 下发（被控端默认 false）。
# 补丁后无论控制端勾什么，被控机退出远程一律不锁屏。
# master 路径 src/server/connection.rs；1.3.9 路径 src/connection.rs（两版文本一致）。
LOCK_RE = re.compile(
    r'if let Ok\(q\) = o\.lock_after_session_end\.enum_value\(\) \{\s*\n'
    r'\s*if q != BoolOption::NotSet \{\s*\n'
    r'\s*self\.lock_after_session_end = q == BoolOption::Yes;\s*\n'
    r'\s*\}\s*\n\s*\}'
)
LOCK_REPL = (
    'if let Ok(q) = o.lock_after_session_end.enum_value() {\n'
    '            if q != BoolOption::NotSet {\n'
    '                // [custom build] v3.7: ignore the controller\'s\n'
    '                // lock-after-session-end request; the controlled PC\n'
    '                // must never auto-lock when the session ends.\n'
    '                self.lock_after_session_end = false;\n'
    '            }\n'
    '        }'
)


def patch_server_conn(root, dry=False):
    print("==> v3.7 P2: 被控端忽略退出锁屏指令 (src/server/connection.rs 或 src/connection.rs)")
    for p in (
        os.path.join(root, "src", "server", "connection.rs"),
        os.path.join(root, "src", "connection.rs"),
    ):
        if patch_file(p, [(LOCK_RE, lambda m: LOCK_REPL)], dry):
            return
    if not dry:
        print("  [WARN] 两个候选路径都不存在，跳过（正常不应发生）")



def patch_rustdesk(root, dry=False):
    print("==> 处理 rustdesk 本体 (KEY 锁死 + 界面精简 + 托盘修复)")
    patch_common(root, dry)
    patch_server_conn(root, dry)

    # 1) KEY 锁死：secure_connection 里始终使用内置 RS_PUB_KEY，忽略用户在设置里填的 key
    client = os.path.join(root, "src", "client.rs")
    patch_file(client, [(
        re.compile(r'get_rs_pk\(\s*if key\.is_empty\(\).*?\}\s*\)', re.DOTALL),
        'get_rs_pk(config::RS_PUB_KEY)',
    )], dry)

    # 2) 隐藏“设置”里的 网络/安全/账户/打印机 四个页签（服务器/key/账号入口全部封闭）
    dsp = os.path.join(root, "flutter", "lib", "desktop", "pages", "desktop_setting_page.dart")
    patch_file(dsp, [
        (re.compile(
            r"if \(!bind\.isDisableSettings\(\) &&\s*\n\s*"
            r"bind\.mainGetBuildinOption\(key: kOptionHideNetworkSetting\) != 'Y'\)\s*\n\s*"
            r"SettingsTabKey\.network,",
            re.DOTALL,
        ), '// SettingsTabKey.network,  (hidden by custom build)'),
        (re.compile(
            r"if \(!isWeb &&\s*\n\s*"
            r"!bind\.isOutgoingOnly\(\) &&\s*\n\s*"
            r"!bind\.isDisableSettings\(\) &&\s*\n\s*"
            r"bind\.mainGetBuildinOption\(key: kOptionHideSecuritySetting\) != 'Y'\)\s*\n\s*"
            r"SettingsTabKey\.safety,",
            re.DOTALL,
        ), '// SettingsTabKey.safety,  (hidden by custom build)'),
        (re.compile(
            r"if \(!bind\.isDisableAccount\(\)\) SettingsTabKey\.account,",
        ), '// SettingsTabKey.account,  (hidden by custom build)'),
        (re.compile(
            r"if \(isWindows\) SettingsTabKey\.printer,",
        ), '// SettingsTabKey.printer,  (hidden by custom build)'),
    ], dry)

    # 3) connection_page.dart：
    #    a) 隐藏主界面的“ID/中继服务器”输入框（setupServerWidget）
    #    b) 【v3.5·问题3 主修复】把 PeerTabPage 从布局中直接移除——
    #       “控制远程桌面”下方的 5 个浏览标签页（最近访问过/收藏/已发现/地址簿/
    #       可访问的设备）不再渲染。布局层面移除后，无论模型逻辑如何变化都不会显示。
    cp = os.path.join(root, "flutter", "lib", "desktop", "pages", "connection_page.dart")
    patch_file(cp, [
        (re.compile(r'offstage:\s*!\(!_svcStopped.*?\),', re.DOTALL),
         'offstage: true,'),
        (re.compile(r'Expanded\(child: PeerTabPage\(\)\),'),
         '// [custom build] 5 个浏览标签页（最近/收藏/已发现/地址簿/可访问的设备）已移除'),
    ], dry)

    # 4) 主页面只保留「你的桌面」标题+简介、ID 面板、固定密码面板。
    hp = os.path.join(root, "flutter", "lib", "desktop", "pages", "desktop_home_page.dart")
    patch_file(hp, [(
        re.compile(
            r"    final children = <Widget>\[(.*?)\n    \];\n",
            re.DOTALL,
        ),
        "    final children = <Widget>[\n"
        "      buildTip(context),\n"
        "      if (!isOutgoingOnly) buildIDBoard(context),\n"
        "      if (!isOutgoingOnly) buildPasswordBoard(context),\n"
        "    ];\n",
    )], dry)

    # 5) 【v3.5·问题3 辅修复】PeerTabModel 全部标签禁用。
    #    旧正则按内容精确匹配（true, true, !isWeb, ...），新版源码第三项变成了
    #    "!isWeb && bind.mainGetLocalOption(key: \"disable-discovery-panel\") != \"Y\"",
    #    导致正则失配、补丁被静默跳过——这就是上一版构建后标签页仍然显示的原因。
    #    现改为结构匹配：只匹配 List.from([ ... ]); 这个初始化形式本身，
    #    内容随便变都能命中。与上面的布局移除形成双保险。
    ptm = os.path.join(root, "flutter", "lib", "models", "peer_tab_model.dart")
    patch_file(ptm, [(
        re.compile(r'List<bool> isEnabled = List\.from\(\[[^\]]*\]\);'),
        'List<bool> isEnabled = List.filled(maxTabCount, false);  // [custom build] 隐藏全部标签页',
    )], dry)

    # 6) 【v3.5·问题2 主修复】托盘图标。
    #    Windows 上托盘是【独立进程】(rustdesk.exe --tray)，主程序只在
    #    “服务进程(--server/服务) 已在运行”时才会拉起它（core_main.rs 启动早期）。
    #    便携版（解压后直接双击 rustdesk.exe、未安装 Windows 服务）永远不满足该条件，
    #    所以右下角从来不会出现图标；主窗口隐藏后也就无法再打开。
    #    修复：去掉“服务已运行”前置条件——只要托盘进程没在跑，启动主程序时就拉起它。
    #    已知三种源码形态全部覆盖：
    #      1.3.9:      check_process("--server", false) && !check_process("--tray", true)
    #      1.4.x:      is_server_running && !check_process("--tray", true)
    #      更新 master: should_check_start_tray && !check_process("--tray", true)
    #
    # 6a) 【v3.6·问题5 主修复一】被控服务改由托盘进程承载。
    #     便携版原逻辑：无参数启动时 std::thread::spawn(start_server) —— 被控服务
    #     是主界面进程内的一个线程，主界面退出它就死（这正是“关闭窗口后无法远程、
    #     已连接断开”的根源；而托盘图标是独立进程还挂着，造成“服务在跑”的假象）。
    #     修复：主界面进程不再自己跑 server 线程，改为确保托盘进程在跑（托盘进程
    #     承载 server，见 6b）。run_me 失败时保留线程版兜底。
    #
    # 6b) 【v3.6·问题5 主修复二】托盘进程承载被控服务 + 注册开机自启。
    #     --tray 分支：在启动托盘图标前 spawn server 线程（托盘进程永不退出，
    #     被控因此常驻），并把自己写入注册表 Run 键（幂等：路径变化时刷新），
    #     开机登录后以 --tray 静默待机（右下角图标 + 被控在线，不弹主窗口）。
    cm = os.path.join(root, "src", "core_main.rs")
    p2_re = re.compile(
        r'else if args\[0\] == "--tray" \{\s*\n\s*'
        r'if !crate::check_process\("--tray", true\) \{\s*\n\s*'
        r'crate::tray::start_tray\(\);\s*\n\s*\}\s*\n\s*'
        r'return None;\s*\n\s*\}'
    )
    p2_repl = (
        'else if args[0] == "--tray" {\n'
        '    // [custom build] v3.6: 托盘进程承载被控服务 + 注册开机自启\n'
        '    if !crate::check_process("--tray", true) {\n'
        '        std::thread::spawn(move || crate::start_server(false, false));\n'
        '        #[cfg(windows)]\n'
        '        {\n'
        '            use winreg::{enums::*, RegKey};\n'
        '            let hkcu = RegKey::predef(HKEY_CURRENT_USER);\n'
        '            if let (Ok(cur_exe), Ok((key, _))) = (\n'
        '                std::env::current_exe(),\n'
        '                hkcu.create_subkey("Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run"),\n'
        '            ) {\n'
        '                let want: String = format!("\\"{}\\" --tray", cur_exe.to_string_lossy());\n'
        '                let cur: String = key\n'
        '                    .get_value(crate::get_app_name())\n'
        '                    .unwrap_or_default();\n'
        '                if cur != want {\n'
        '                    let _ = key.set_value(crate::get_app_name(), &want);\n'
        '                }\n'
        '            }\n'
        '        }\n'
        '        crate::tray::start_tray();\n'
        '    }\n'
        '    return None;\n'
        '}'
    )
    patch_file(cm, [
        # v3.5：三种源码形态的托盘拉起条件 → 无条件
        (re.compile(
            r'crate::check_process\("--server", false\) && !crate::check_process\("--tray", true\)'
        ), '!crate::check_process("--tray", true)'),
        (re.compile(
            r'(?:is_server_running|should_check_start_tray) && !crate::check_process\("--tray", true\)'
        ), '!crate::check_process("--tray", true)'),
        # v3.6 P1：主界面进程不再跑 server 线程（1.3.9 与 master 此行文本一致、全文件唯一；
        #          macos 分支的同名调用参数不同 (true, false)，不会误匹配）
        (re.compile(
            r'std::thread::spawn\(move \|\| crate::start_server\(false, no_server\)\);'
        ),
         '// [custom build] v3.6: 便携版被控服务由 --tray 进程承载，主界面退出不影响被控\n'
         '        if !crate::check_process("--tray", true) {\n'
         '            if crate::run_me(vec!["--tray"]).is_err() {\n'
         '                std::thread::spawn(move || crate::start_server(false, no_server));\n'
         '            }\n'
         '        }'),
        # v3.6 P2：--tray 分支承载 server + 注册开机自启（锚定 else if args[0] == "--tray"，
        #          不会碰到启动分支里 v3.5 改出来的同名 if）。
        #          注意：用 lambda 函数替换而非模板字符串——re.subn 的模板会把 "\\"
        #          再解释一次导致写入 Rust 源码的反斜杠数减半（变成非法转义），
        #          函数返回值则按字面写入，p2_repl 里写的就是最终文件内容。
        (p2_re,
         lambda m: p2_repl),
    ], dry)

    # 7) 主窗口关闭时最小化到系统托盘（v3.4 已生效，保留）：
    #    onWindowClose -> windowManager.hide()，进程与服务继续运行。
    # 8) 被控端无感：强制隐藏“连接管理/连接状态”窗口（v3.4 已生效，保留）。
    m = os.path.join(root, "flutter", "lib", "main.dart")
    patch_file(m, [
        (re.compile(r"class _AppState extends State<App> with WidgetsBindingObserver \{"),
         "class _AppState extends State<App> with WidgetsBindingObserver, WindowListener {"),
        (re.compile(r"WidgetsBinding\.instance\.addObserver\(this\);"),
         "WidgetsBinding.instance.addObserver(this);\n    windowManager.addListener(this);"),
        (re.compile(r"WidgetsBinding\.instance\.removeObserver\(this\);"),
         "WidgetsBinding.instance.removeObserver(this);\n    windowManager.removeListener(this);"),
        (re.compile(r"  @override\n  void didChangeMetrics\(\) \{"),
         "  @override\n"
         "  Future<void> onWindowClose() async {\n"
         "    // [custom build] 关闭窗口 -> 最小化到系统托盘，不退出进程\n"
         "    await windowManager.hide();\n"
         "  }\n\n"
         "  @override\n"
         "  void didChangeMetrics() {"),
        (re.compile(r"\s*final hide = await bind\.cmGetConfig\(name: \"hide_cm\"\) == 'true';"),
         "  final hide = true;  // [custom build] 强制隐藏连接管理窗口（被控端无感）"),
        (re.compile(r"showCmWindow\(\{bool isStartup = false\}\) async \{.*?\n\}\n", re.DOTALL),
         "// [custom build] 被控端无感：任何“显示连接管理窗口”的请求都改为隐藏\n"
         "showCmWindow({bool isStartup = false}) async {\n"
         "  await hideCmWindow(isStartup: isStartup);\n"
         "}\n"),
    ], dry)


# ---------- v3.5：补丁后强制校验（防“静默失配”） ----------
def verify_patches(rs_root, hbb_root=None, server="", key=""):
    """补丁全部打完后立刻校验关键特征。
    CRITICAL 项失配 -> 打印原因并返回 False（调用方 exit 1，构建当场失败）；
    WARNING  项失配 -> 只打印警告（不影响构建，但提示哪些定制可能没生效）。"""
    print("==> 校验补丁结果（v3.7 防静默失配检查，含固定密码/退出锁屏/常驻被控）")

    critical_errors = []
    warn_errors = []

    def check(label, path, conds):
        if not path or not os.path.exists(path):
            critical_errors.append(f"[{label}] 文件不存在: {path}")
            return
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        for pattern, should_exist in conds:
            found = re.search(pattern, text) is not None
            if should_exist and not found:
                (critical_errors if label.startswith("CRIT") else warn_errors).append(
                    f"[{label}] 预期出现但未找到: {pattern}")
            elif not should_exist and found:
                (critical_errors if label.startswith("CRIT") else warn_errors).append(
                    f"[{label}] 预期移除但仍存在: {pattern}")

    # ---- CRITICAL：本次两项修复 + 服务器/KEY ----
    # ---- CRITICAL：v3.7 两项修复 ----
    check("CRIT-v3.7 custom.txt 纯 JSON 回退 (src/common.rs)",
          os.path.join(rs_root, "src", "common.rs"), [
              # 回退解析生效标志
              (r'parsed = serde_json::from_str\(config\)\.ok\(\);', True),
              # 官方签名路径已改写（不再是无条件 return 的验签失败分支）
              (r'let Ok\(data\) = sign::verify\(&data, &pk\) else', False),
          ])
    lock_paths = [
        os.path.join(rs_root, "src", "server", "connection.rs"),
        os.path.join(rs_root, "src", "connection.rs"),
    ]
    lock_found = [p for p in lock_paths if p and os.path.exists(p)]
    if lock_found:
        check("CRIT-v3.7 被控端忽略退出锁屏 (server/connection.rs)",
              lock_found[0], [
                  (r'self\.lock_after_session_end = false;', True),
                  (r'self\.lock_after_session_end = q == BoolOption::Yes;', False),
              ])
    else:
        critical_errors.append(
            "[CRIT-v3.7 被控端忽略退出锁屏] src/server/connection.rs 与 src/connection.rs 均不存在")
    check("CRIT-问题2 托盘无条件拉起 (src/core_main.rs)",
          os.path.join(rs_root, "src", "core_main.rs"), [
              (r'check_process\("--server", false\) && !crate::check_process\("--tray"', False),
              (r'is_server_running && !crate::check_process\("--tray"', False),
              (r'should_check_start_tray && !crate::check_process\("--tray"', False),
              # 替换成功的标志：启动分支的 if 后紧跟 linux cfg（--tray 分支的 if 后是 start_tray）
              (r'if !crate::check_process\("--tray", true\) \{\s*\n\s*#\[cfg\(target_os = "linux"\)\]',
               True),
          ])
    check("CRIT-问题5 被控常驻托盘进程+开机自启 (src/core_main.rs)",
          os.path.join(rs_root, "src", "core_main.rs"), [
              # P1 生效标志：主界面不再无条件跑 server 线程（兜底分支仍在，但带注释前缀）
              (r'// \[custom build\] v3\.6: 便携版被控服务由 --tray 进程承载，主界面退出不影响被控', True),
              # P2 生效标志：--tray 分支的 server 线程、自启注册
              (r'// \[custom build\] v3\.6: 托盘进程承载被控服务 \+ 注册开机自启', True),
              (r'std::thread::spawn\(move \|\| crate::start_server\(false, false\)\);', True),
              (r'use winreg::\{enums::\*, RegKey\};', True),
              (r'create_subkey\("Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run"\)', True),
              (r'if crate::run_me\(vec!\["--tray"\]\)\.is_err\(\)', True),
          ])
    check("CRIT-问题3 标签页布局移除 (connection_page.dart)",
          os.path.join(rs_root, "flutter", "lib", "desktop", "pages", "connection_page.dart"), [
              (r'Expanded\(child: PeerTabPage\(\)\)', False),
          ])
    check("CRIT-问题3 标签页模型禁用 (peer_tab_model.dart)",
          os.path.join(rs_root, "flutter", "lib", "models", "peer_tab_model.dart"), [
              (r'List<bool> isEnabled = List\.filled\(maxTabCount, false\)', True),
          ])
    check("CRIT-问题2/4 主窗口关闭到托盘+无感连接 (main.dart)",
          os.path.join(rs_root, "flutter", "lib", "main.dart"), [
              (r'Future<void> onWindowClose\(\) async', True),
              (r'final hide = true;', True),
              (r'await hideCmWindow\(isStartup: isStartup\);', True),
          ])
    if hbb_root:
        hp = os.path.join(hbb_root, "src", "config.rs")
        conds = []
        if server:
            conds.append((re.escape(f'RENDEZVOUS_SERVERS: &[&str] = &["{server}"];'), True))
        if key:
            conds.append((re.escape(f'RS_PUB_KEY: &str = "{key}";'), True))
        if conds:
            check("CRIT-服务器地址/KEY 内置 (hbb_common config.rs)", hp, conds)

    # ---- WARNING：历史定制点（v3.3/v3.4 已验证生效；若未来源码变化失配则提醒） ----
    check("WARN-主页面精简 (desktop_home_page.dart)",
          os.path.join(rs_root, "flutter", "lib", "desktop", "pages", "desktop_home_page.dart"), [
              # 注意：loadPowered/loadLogo 等方法定义仍留在文件里（只是 children 不再引用），
              # 不能对方法名做“不存在”检查，只检查 children 数组已按预期重写。
              (r'final children = <Widget>\[\s*\n\s*buildTip\(context\),', True),
          ])
    check("WARN-设置页签隐藏 (desktop_setting_page.dart)",
          os.path.join(rs_root, "flutter", "lib", "desktop", "pages", "desktop_setting_page.dart"), [
              (r'//\s*SettingsTabKey\.network,', True),
              (r'//\s*SettingsTabKey\.safety,', True),
              (r'//\s*SettingsTabKey\.account,', True),
              (r'//\s*SettingsTabKey\.printer,', True),
          ])
    check("WARN-服务器输入框隐藏 (connection_page.dart)",
          os.path.join(rs_root, "flutter", "lib", "desktop", "pages", "connection_page.dart"), [
              (r'offstage: true,', True),
          ])
    if hbb_root:
        check("WARN-toml 行为选项预设生效 (get_or)",
              os.path.join(hbb_root, "src", "config.rs"), [
                  (r'\.or\(HARD_SETTINGS\.read\(\)\.unwrap\(\)\.get\(k\)\)', True),
              ])

    if warn_errors:
        print("  [WARN] 以下定制点未命中（不影响构建，但对应功能可能没生效）：")
        for e in warn_errors:
            print(f"    - {e}")
    if critical_errors:
        print("  [FAIL] 关键补丁未生效，中止（请把下面几行发给维护者）：")
        for e in critical_errors:
            print(f"    - {e}")
        print("\n校验未通过 ✗  为避免白等 2 小时构建出未修复的版本，已提前终止。")
        return False
    print("  校验通过 ✓  所有关键补丁均已生效。")
    return True


def cmd_all(root, server, key, dry):
    hbb = os.path.join(root, "libs", "hbb_common")
    hbb = hbb if os.path.isdir(os.path.join(hbb, "src")) else root
    patch_hbb(hbb, server, key, dry)
    patch_rustdesk(root, dry)
    if not dry:
        if not verify_patches(root, hbb, server, key):
            sys.exit(1)


# ---------- 自检 ----------
def selftest():
    tmp = tempfile.mkdtemp(prefix="rustdesk_selftest_")
    try:
        # hbb_common/src/config.rs
        hbb_src = os.path.join(tmp, "hbb", "src")
        os.makedirs(hbb_src)
        with open(os.path.join(hbb_src, "config.rs"), "w", encoding="utf-8") as f:
            f.write(
                'pub const RENDEZVOUS_SERVERS: &[&str] = &["rs-ny.rustdesk.com"];\n'
                'pub const RENDEZVOUS_PORT: i32 = 21116;\n'
                'pub const RELAY_PORT: i32 = 21117;\n'
                'pub const RS_PUB_KEY: &str = "OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw=";\n'
                'fn get_or(&self, k: &str, default: &str) -> String {\n'
                '    if let Some(v) = OVERWRITE\n'
                '        .read()\n'
                '        .unwrap()\n'
                '        .get(k)\n'
                '        .map(|v| v.to_string())\n'
                '        .or(c.read().unwrap().get(k))\n'
                '        .map(|v| v.to_string())\n'
                '    {\n'
                '        return v.to_string();\n'
                '    }\n'
                '    default.to_string()\n'
                '}\n'
            )
        # src/client.rs
        rs_src = os.path.join(tmp, "rs", "src")
        os.makedirs(rs_src)
        with open(os.path.join(rs_src, "client.rs"), "w", encoding="utf-8") as f:
            f.write(
                '    async fn secure_connection(\n'
                '        peer_id: &str,\n'
                '        key: &str,\n'
                '        conn: &mut Stream,\n'
                '    ) -> ResultType<Option<Vec<u8>>> {\n'
                '        let rs_pk = get_rs_pk(if key.is_empty() {\n'
                '            config::RS_PUB_KEY\n'
                '        } else {\n'
                '            key\n'
                '        });\n'
                '    }\n'
            )
        # src/core_main.rs —— 覆盖三种已知源码形态 + --tray 分支 + 便携版 server 线程行
        with open(os.path.join(rs_src, "core_main.rs"), "w", encoding="utf-8") as f:
            f.write(
                '#[cfg(any(target_os = "linux", target_os = "windows"))]\n'
                'if args.is_empty() {\n'
                '    if crate::check_process("--server", false) && !crate::check_process("--tray", true) {\n'
                '        #[cfg(target_os = "linux")]\n'
                '        hbb_common::allow_err!(crate::platform::check_autostart_config());\n'
                '        hbb_common::allow_err!(crate::run_me(vec!["--tray"]));\n'
                '    }\n'
                '}\n'
                'fn shape_140() {\n'
                '    let is_server_running = crate::platform::is_self_service_running();\n'
                '    if is_server_running && !crate::check_process("--tray", true) {\n'
                '        hbb_common::allow_err!(crate::run_me(vec!["--tray"]));\n'
                '    }\n'
                '}\n'
                'fn shape_master() {\n'
                '    #[cfg(target_os = "windows")]\n'
                '    let should_check_start_tray = crate::platform::is_self_service_running()\n'
                '        && crate::platform::is_cur_exe_the_installed();\n'
                '    if should_check_start_tray && !crate::check_process("--tray", true) {\n'
                '        hbb_common::allow_err!(crate::run_me(vec!["--tray"]));\n'
                '    }\n'
                '}\n'
                # v3.6 P1 目标行：便携版无参数启动时的 server 线程（1.3.9 与 master 文本一致）
                'fn main_ui_startup() {\n'
                '    if args.is_empty() {\n'
                '        std::thread::spawn(move || crate::start_server(false, no_server));\n'
                '    }\n'
                '}\n'
                # --tray 分支（真实源码为 else if 形态）
                'fn tray_branch() {\n'
                '    if args[0] == "--remove" {\n'
                '        return None;\n'
                '    } else if args[0] == "--tray" {\n'
                '        if !crate::check_process("--tray", true) {\n'
                '            crate::tray::start_tray();\n'
                '        }\n'
                '        return None;\n'
                '    }\n'
                '}\n'
            )
        # v3.7 P1 样例：src/common.rs —— read_custom_client 官方原文本
        # （1.3.9 与 master 逐字一致；仅前半段被补丁替换）
        with open(os.path.join(rs_src, "common.rs"), "w", encoding="utf-8") as f:
            f.write(
                'pub fn read_custom_client(config: &str) {\n'
                '    let Ok(data) = decode64(config) else {\n'
                '        log::error!("Failed to decode custom client config");\n'
                '        return;\n'
                '    };\n'
                '    const KEY: &str = "5Qbwsde3unUcJBtrx9ZkvUmwFNoExHzpryHuPUdqlWM=";\n'
                '    let Some(pk) = get_rs_pk(KEY) else {\n'
                '        log::error!("Failed to parse public key of custom client");\n'
                '        return;\n'
                '    };\n'
                '    let Ok(data) = sign::verify(&data, &pk) else {\n'
                '        log::error!("Failed to dec custom client config");\n'
                '        return;\n'
                '    };\n'
                '    let Ok(mut data) =\n'
                '        serde_json::from_slice::<std::collections::HashMap<String, serde_json::Value>>(&data)\n'
                '    else {\n'
                '        log::error!("Failed to parse custom client config");\n'
                '        return;\n'
                '    };\n'
                '    if let Some(app_name) = data.remove("app-name") {\n'
                '        config::HARD_SETTINGS.write().unwrap().insert("x", "y");\n'
                '    }\n'
                '}\n'
            )
        # v3.7 P2 样例：src/server/connection.rs —— lock_after_session_end 块
        # （master 路径；1.3.9 在 src/connection.rs，文本一致）
        sc = os.path.join(rs_src, "server")
        os.makedirs(sc)
        with open(os.path.join(sc, "connection.rs"), "w", encoding="utf-8") as f:
            f.write(
                'fn update_option(o: &OptionMessage) {\n'
                '        if let Some(q) = o.supported_decoding.clone().take() {\n'
                '        }\n'
                '        if let Ok(q) = o.lock_after_session_end.enum_value() {\n'
                '            if q != BoolOption::NotSet {\n'
                '                self.lock_after_session_end = q == BoolOption::Yes;\n'
                '            }\n'
                '        }\n'
                '        if let Ok(q) = o.show_remote_cursor.enum_value() {\n'
                '        }\n'
                '}\n'
            )
        # desktop_setting_page.dart
        pages = os.path.join(tmp, "rs", "flutter", "lib", "desktop", "pages")
        os.makedirs(pages)
        with open(os.path.join(pages, "desktop_setting_page.dart"), "w", encoding="utf-8") as f:
            f.write(
                '  static final List<SettingsTabKey> tabKeys = [\n'
                '    if (bind.mainGetBuildinOption(key: kOptionHideGeneralSetting) != \'Y\')\n'
                '      SettingsTabKey.general,\n'
                '    if (!bind.isDisableSettings() &&\n'
                '        bind.mainGetBuildinOption(key: kOptionHideNetworkSetting) != \'Y\')\n'
                '      SettingsTabKey.network,\n'
                '    if (!isWeb &&\n'
                '        !bind.isOutgoingOnly() &&\n'
                '        !bind.isDisableSettings() &&\n'
                '        bind.mainGetBuildinOption(key: kOptionHideSecuritySetting) != \'Y\')\n'
                '      SettingsTabKey.safety,\n'
                '    if (!bind.isIncomingOnly()) SettingsTabKey.display,\n'
                '    SettingsTabKey.plugin,\n'
                '    if (!bind.isDisableAccount()) SettingsTabKey.account,\n'
                '    if (isWindows) SettingsTabKey.printer,\n'
                '    SettingsTabKey.about,\n'
                '  ];\n'
            )
        # connection_page.dart（含 v3.5 要移除的 PeerTabPage）
        with open(os.path.join(pages, "connection_page.dart"), "w", encoding="utf-8") as f:
            f.write(
                '  Widget setupServerWidget() => Flexible(\n'
                '    child: Offstage(\n'
                '      offstage: !(!_svcStopped.value && stateGlobal.svcStatus.value == SvcStatus.ready && _svcIsUsingPublicServer.value),\n'
                '      child: Row(\n'
                '        crossAxisAlignment: CrossAxisAlignment.center,\n'
                '        children: [],\n'
                '      ),\n'
                '    ),\n'
                '  );\n\n'
                '  Widget build(BuildContext context) {\n'
                '    return Column(\n'
                '      children: [\n'
                '        Expanded(\n'
                '            child: Column(\n'
                '          children: [\n'
                '            Row(\n'
                '              children: [\n'
                '                Flexible(child: _buildRemoteIDTextField(context)),\n'
                '              ],\n'
                '            ).marginOnly(top: 22),\n'
                '            SizedBox(height: 12),\n'
                '            Divider().paddingOnly(right: 12),\n'
                '            Expanded(child: PeerTabPage()),\n'
                '          ],\n'
                '        ).paddingOnly(left: 12.0)),\n'
                '      ],\n'
                '    );\n'
                '  }\n'
            )
        with open(os.path.join(pages, "desktop_home_page.dart"), "w", encoding="utf-8") as f:
            f.write(
                '  Widget buildLeftPane(BuildContext context) {\n'
                '    final isIncomingOnly = bind.isIncomingOnly();\n'
                '    final isOutgoingOnly = bind.isOutgoingOnly();\n'
                '    final children = <Widget>[\n'
                '      if (!isOutgoingOnly) buildPresetPasswordWarning(),\n'
                '      if (bind.isCustomClient())\n'
                '        Align(\n'
                '          alignment: Alignment.center,\n'
                '          child: loadPowered(context),\n'
                '        ),\n'
                '      Align(\n'
                '        alignment: Alignment.center,\n'
                '        child: loadLogo(),\n'
                '      ),\n'
                '      buildTip(context),\n'
                '      if (!isOutgoingOnly) buildIDBoard(context),\n'
                '      buildHelpCards,\n'
                '      buildPluginEntry(),\n'
                '    ];\n'
                '  }\n'
            )

        # peer_tab_model.dart —— 用【新版 master 风格】做样例（含 disable-discovery-panel，
        # 旧正则正是在这种结构上失配的），宽松正则必须能吃下它
        models = os.path.join(tmp, "rs", "flutter", "lib", "models")
        os.makedirs(models)
        with open(os.path.join(models, "peer_tab_model.dart"), "w", encoding="utf-8") as f:
            f.write(
                "class PeerTabModel with ChangeNotifier {\n"
                "  static const int maxTabCount = 5;\n"
                "  List<bool> isEnabled = List.from([\n"
                "    true,\n"
                "    true,\n"
                "    !isWeb && bind.mainGetLocalOption(key: \"disable-discovery-panel\") != \"Y\",\n"
                "    !(bind.isDisableAb() || bind.isDisableAccount()),\n"
                "    !(bind.isDisableGroupPanel() || bind.isDisableAccount()),\n"
                "  ]);\n"
                "}\n"
            )
        # main.dart
        libdir = os.path.join(tmp, "rs", "flutter", "lib")
        os.makedirs(libdir, exist_ok=True)
        with open(os.path.join(libdir, "main.dart"), "w", encoding="utf-8") as f:
            f.write(
                "class _AppState extends State<App> with WidgetsBindingObserver {\n"
                "  @override\n  void initState() {\n"
                "    super.initState();\n"
                "    WidgetsBinding.instance.addObserver(this);\n"
                "  }\n\n"
                "  @override\n  void dispose() {\n"
                "    WidgetsBinding.instance.removeObserver(this);\n"
                "    super.dispose();\n"
                "  }\n\n"
                "  @override\n  void didChangeMetrics() {\n"
                "    _updateOrientation();\n"
                "  }\n\n"
                "void runConnectionManagerScreen() async {\n"
                "  final hide = await bind.cmGetConfig(name: \"hide_cm\") == 'true';\n"
                "}\n\n"
                "showCmWindow({bool isStartup = false}) async {\n"
                "  if (isStartup) {\n"
                "    await windowManager.show();\n"
                "  } else if (_isCmReadyToShow) {\n"
                "    await windowManager.show();\n"
                "  }\n"
                "}\n"
            )

        patch_hbb(os.path.join(tmp, "hbb"), "my.rustdesk.com:21116", "MYKEY123", dry=False)
        patch_rustdesk(os.path.join(tmp, "rs"), dry=False)

        c = open(os.path.join(hbb_src, "config.rs"), encoding="utf-8").read()
        assert 'RENDEZVOUS_SERVERS: &[&str] = &["my.rustdesk.com:21116"];' in c, "server 替换失败"
        assert 'RS_PUB_KEY: &str = "MYKEY123";' in c, "key 替换失败"

        cl = open(os.path.join(rs_src, "client.rs"), encoding="utf-8").read()
        assert 'get_rs_pk(config::RS_PUB_KEY);' in cl, "key 锁死失败"

        # core_main.rs：三种形态的条件全部被剥离，--tray 分支被 v3.6 增强但 start_tray 保留
        cm = open(os.path.join(rs_src, "core_main.rs"), encoding="utf-8").read()
        assert 'check_process("--server", false) &&' not in cm, "1.3.9 形态托盘条件未剥离"
        assert 'is_server_running && !crate::check_process' not in cm, "1.4.0 形态托盘条件未剥离"
        assert 'should_check_start_tray && !crate::check_process' not in cm, "master 形态托盘条件未剥离"
        assert cm.count('if !crate::check_process("--tray", true) {') == 5, "托盘条件替换计数不符"
        assert 'crate::tray::start_tray();' in cm, "--tray 分支被误改"
        # v3.6 P1：主界面不再直接跑 server 线程（仅留 run_me 失败兜底）
        assert '主界面退出不影响被控' in cm, "P1 注释缺失（便携版 server 线程替换失败）"
        assert 'if crate::run_me(vec!["--tray"]).is_err()' in cm, "P1 兜底分支缺失"
        # v3.6 P2：托盘进程承载 server + 注册开机自启
        assert '托盘进程承载被控服务 + 注册开机自启' in cm, "P2 注释缺失（--tray 分支替换失败）"
        assert 'std::thread::spawn(move || crate::start_server(false, false));' in cm, "P2 server 线程缺失"
        assert 'use winreg::{enums::*, RegKey};' in cm, "P2 winreg 导入缺失"
        assert 'CurrentVersion\\\\Run' in cm, "P2 注册表 Run 路径缺失"
        assert 'hkcu.create_subkey' in cm, "P2 create_subkey 缺失"

        # v3.7 P1：custom.txt 纯 JSON 回退
        cmn = open(os.path.join(rs_src, "common.rs"), encoding="utf-8").read()
        assert 'parsed = serde_json::from_str(config).ok();' in cmn, "v3.7 P1 纯 JSON 回退缺失"
        assert 'if parsed.is_none()' in cmn, "v3.7 P1 回退分支缺失"
        assert 'sign::verify(&data, &pk) else' not in cmn, "v3.7 P1 官方验签硬失败分支未替换"
        assert 'data.remove("app-name")' in cmn, "v3.7 P1 补丁误伤函数后半段"
        # v3.7 P2：被控端忽略退出锁屏
        scn = open(os.path.join(sc, "connection.rs"), encoding="utf-8").read()
        assert 'self.lock_after_session_end = false;' in scn, "v3.7 P2 锁屏忽略缺失"
        assert 'q == BoolOption::Yes' not in scn, "v3.7 P2 原锁屏赋值残留"
        assert 'show_remote_cursor.enum_value()' in scn, "v3.7 P2 误伤相邻选项块"

        dsp = open(os.path.join(pages, "desktop_setting_page.dart"), encoding="utf-8").read()
        assert '// SettingsTabKey.network,  (hidden by custom build)' in dsp, "网络页签隐藏失败"
        assert '// SettingsTabKey.safety,  (hidden by custom build)' in dsp, "安全页签隐藏失败"
        assert '// SettingsTabKey.account,  (hidden by custom build)' in dsp, "账户页签隐藏失败"
        assert '// SettingsTabKey.printer,  (hidden by custom build)' in dsp, "打印机页签隐藏失败"

        cp = open(os.path.join(pages, "connection_page.dart"), encoding="utf-8").read()
        assert 'offstage: true,' in cp, "服务器输入框隐藏失败"
        assert 'Expanded(child: PeerTabPage())' not in cp, "PeerTabPage 未从布局移除"

        hp = open(os.path.join(pages, "desktop_home_page.dart"), encoding="utf-8").read()
        assert 'buildIDBoard(context)' in hp, "主页面 ID 面板缺失"
        assert 'buildTip(context)' in hp, "主页面“你的桌面”标题/简介未保留"
        assert 'loadPowered' not in hp, "主页面 Powered by 未移除"
        assert 'buildHelpCards' not in hp, "主页面帮助卡片未移除"

        ptm = open(os.path.join(models, "peer_tab_model.dart"), encoding="utf-8").read()
        assert 'List.filled(maxTabCount, false)' in ptm, "5 个标签页未禁用（master 风格样例）"
        assert 'List.from([' not in ptm, "isEnabled 未被替换"

        m = open(os.path.join(libdir, "main.dart"), encoding="utf-8").read()
        assert 'with WidgetsBindingObserver, WindowListener {' in m, "WindowListener 未添加"
        assert 'windowManager.addListener(this);' in m, "addListener 未添加"
        assert 'windowManager.removeListener(this);' in m, "removeListener 未添加"
        assert 'Future<void> onWindowClose() async' in m, "onWindowClose 未添加"
        assert 'final hide = true;' in m, "连接管理窗口未强制隐藏"
        assert 'await hideCmWindow(isStartup: isStartup);' in m, "showCmWindow 未重定向为隐藏"
        assert 'bind.cmGetConfig(name: "hide_cm")' not in m, "cm 配置判断残留"

        # verify_patches 必须全绿
        assert verify_patches(os.path.join(tmp, "rs"), os.path.join(tmp, "hbb"),
                              "my.rustdesk.com:21116", "MYKEY123"), "强制校验未通过"

        print("SELFTEST PASSED ✓  所有正则均命中当前源码结构（含新版 master 风格），替换与校验正确。")
        return True
    except AssertionError as e:
        print("SELFTEST FAILED ✗", e)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="RustDesk Windows 定制补丁 v3.7")
    ap.add_argument("target", choices=["all", "hbb", "rustdesk", "selftest"])
    ap.add_argument("--path", default=".")
    ap.add_argument("--server", default="")
    ap.add_argument("--key", default="")
    ap.add_argument("--config", default="", help="可选：从 custom.json 读取 server/key")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.config and os.path.isfile(args.config):
        try:
            import json
            with open(args.config, encoding="utf-8") as f:
                d = json.load(f)
            args.server = args.server or d.get("server", "")
            args.key = args.key or d.get("key", "")
        except Exception as e:
            print(f"[WARN] 读取 {args.config} 失败: {e}")

    if args.target == "selftest":
        sys.exit(0 if selftest() else 1)

    if not os.path.isdir(args.path):
        print(f"路径不存在: {args.path}")
        sys.exit(1)

    dry = args.dry_run
    if args.target == "hbb":
        patch_hbb(args.path, args.server, args.key, dry)
        if not dry and not verify_patches(None, args.path, args.server, args.key):
            sys.exit(1)
    elif args.target == "rustdesk":
        patch_rustdesk(args.path, dry)
        if not dry and not verify_patches(args.path, None, "", ""):
            sys.exit(1)
    elif args.target == "all":
        cmd_all(args.path, args.server, args.key, dry)
    print("\n完成。建议用 `git diff` 复查改动后再提交/编译。")


if __name__ == "__main__":
    main()
