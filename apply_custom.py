#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RustDesk Windows 定制补丁脚本（跨平台，Python 3.8+）
=====================================================
作用：
  1. 把自建 ID/中继服务器地址和公钥 KEY 烧进源码（hbb_common/src/config.rs）
  2. 锁死 KEY，使客户端不使用用户在“设置-网络”里填写的 key（始终用内置 RS_PUB_KEY）
  3. 让 RustDesk.toml 的 [options] 预设真正生效（修补 hbb_common 的 get_or，
     把 HARD_SETTINGS 作为「预设」插在 LOCAL 与 DEFAULT 之间；否则 toml 里的
     verification-method/approve-mode/access-mode/direct-server 等行为选项
     对全新客户端无效）
  4. 精简界面：
       - 隐藏“设置”里的 网络/安全/账户/打印机 四个页签
       - 隐藏主界面上的“ID/中继服务器”输入框
       - 主页面只保留“你的桌面”(ID+固定密码面板) 与右侧“控制远程桌面”

用法（在 rustdesk 仓库根目录运行）：
  python apply_custom.py all --path . --server "rustdesk.example.com:21116" --key "你的公钥"
  python apply_custom.py hbb      --path libs/hbb_common --server "..." --key "..."
  python apply_custom.py rustdesk --path .
  python apply_custom.py selftest        # 用内置样例验证正则是否匹配当前源码结构

说明：
  --path 对 all / rustdesk 指向 rustdesk 仓库根；对 hbb 指向 hbb_common 仓库根。
  不指定 --server/--key 时仅做界面精简，不写服务器/KEY（可用占位后补）。
  加 --dry-run 只打印将要改动、不写文件。
"""
import os
import re
import sys
import io
import argparse
import tempfile
import shutil

# ---- 关键：强制把 stdout/stderr 设成 UTF-8，避免 Windows cp1252 控制台打印中文崩溃 ----
# 兼容 Python 3.7+；reconfigure 在 3.7 就有；CI / GitHub Actions 的 Windows runner 默认 cp936/cp1252。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # 极少数环境下 reconfigure 失败，再用底层兜底
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
    #    页签隐藏项 (hide-*-settings / disable-account) 由 HARD_SETTINGS 直读，
    #    本补丁对它们无副作用。
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


# ---------- rustdesk 本体（KEY 锁死 + 界面精简） ----------
def patch_rustdesk(root, dry=False):
    print("==> 处理 rustdesk 本体 (KEY 锁死 + 界面精简)")

    # 1) KEY 锁死：secure_connection 里始终使用内置 RS_PUB_KEY，忽略用户在设置里填的 key
    client = os.path.join(root, "src", "client.rs")
    patch_file(client, [(
        re.compile(r'get_rs_pk\(\s*if key\.is_empty\(\).*?\}\s*\)', re.DOTALL),
        'get_rs_pk(config::RS_PUB_KEY)',
    )], dry)

    # 2) 隐藏“设置”里的 网络/安全/账户/打印机 四个页签（服务器/key/账号入口全部封闭）
    #    注意：这些项多为 `if (...) ... SettingsTabKey.xxx,` 结构，只注释 SettingsTabKey
    #    会留下悬空 if 导致 Dart 编译失败，因此连同整个 if 条件一起注释掉。
    #    其中 安全/网络 页签另有 toml (hide-*-settings) 双保险；账户页另有 toml
    #    (disable-account) 双保险；打印机页在 Windows 上无选项钩子，只能靠本源码补丁。
    dsp = os.path.join(root, "flutter", "lib", "desktop", "pages", "desktop_setting_page.dart")
    patch_file(dsp, [
        # 2a) 网络页签
        (re.compile(
            r"if \(!bind\.isDisableSettings\(\) &&\s*\n\s*"
            r"bind\.mainGetBuildinOption\(key: kOptionHideNetworkSetting\) != 'Y'\)\s*\n\s*"
            r"SettingsTabKey\.network,",
            re.DOTALL,
        ), '// SettingsTabKey.network,  (hidden by custom build)'),
        # 2b) 安全页签（IP 直接访问等已通过 RustDesk.toml 锁进配置）
        #     真实 1.3.x 源码里 safety 项前有 !isWeb && !isOutgoingOnly() &&
        #     !isDisableSettings() && 三个条件，整段一起注释掉（避免悬空 if）。
        (re.compile(
            r"if \(!isWeb &&\s*\n\s*"
            r"!bind\.isOutgoingOnly\(\) &&\s*\n\s*"
            r"!bind\.isDisableSettings\(\) &&\s*\n\s*"
            r"bind\.mainGetBuildinOption\(key: kOptionHideSecuritySetting\) != 'Y'\)\s*\n\s*"
            r"SettingsTabKey\.safety,",
            re.DOTALL,
        ), '// SettingsTabKey.safety,  (hidden by custom build)'),
        # 2c) 账户页签
        (re.compile(
            r"if \(!bind\.isDisableAccount\(\)\) SettingsTabKey\.account,",
        ), '// SettingsTabKey.account,  (hidden by custom build)'),
        # 2d) 打印机页签（Windows 上无选项钩子，只能改源码隐藏）
        (re.compile(
            r"if \(isWindows\) SettingsTabKey\.printer,",
        ), '// SettingsTabKey.printer,  (hidden by custom build)'),
    ], dry)

    # 3) 隐藏主界面的“ID/中继服务器”输入框（setupServerWidget）
    cp = os.path.join(root, "flutter", "lib", "desktop", "pages", "connection_page.dart")
    patch_file(cp, [(
        re.compile(r'offstage:\s*!\(!_svcStopped.*?\),', re.DOTALL),
        'offstage: true,',
    )], dry)

    # 4) 主页面只保留「你的桌面」(ID + 固定密码面板) 与右侧「控制远程桌面」，
    #    移除 Powered by / Logo / 提示 / 帮助卡片 / 插件入口等其它元素。
    hp = os.path.join(root, "flutter", "lib", "desktop", "pages", "desktop_home_page.dart")
    patch_file(hp, [(
        re.compile(
            r"    final children = <Widget>\[(.*?)\n    \];\n",
            re.DOTALL,
        ),
        "    final children = <Widget>[\n"
        "      if (!isOutgoingOnly) buildIDBoard(context),\n"
        "      if (!isOutgoingOnly) buildPasswordBoard(context),\n"
        "    ];\n",
    )], dry)


def cmd_all(root, server, key, dry):
    hbb = os.path.join(root, "libs", "hbb_common")
    # hbb_common 可能作为子模块在 libs/hbb_common；也可能单独仓库
    patch_hbb(hbb if os.path.isdir(os.path.join(hbb, "src")) else root, server, key, dry)
    patch_rustdesk(root, dry)


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
                '  );\n'
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

        patch_hbb(os.path.join(tmp, "hbb"), "my.rustdesk.com:21116", "MYKEY123", dry=False)
        patch_rustdesk(os.path.join(tmp, "rs"), dry=False)

        c = open(os.path.join(hbb_src, "config.rs"), encoding="utf-8").read()
        assert 'RENDEZVOUS_SERVERS: &[&str] = &["my.rustdesk.com:21116"];' in c, "server 替换失败"
        assert 'RS_PUB_KEY: &str = "MYKEY123";' in c, "key 替换失败"

        cl = open(os.path.join(rs_src, "client.rs"), encoding="utf-8").read()
        assert 'get_rs_pk(config::RS_PUB_KEY);' in cl, "key 锁死失败"

        dsp = open(os.path.join(pages, "desktop_setting_page.dart"), encoding="utf-8").read()
        assert '// SettingsTabKey.network,  (hidden by custom build)' in dsp, "网络页签隐藏失败"
        assert 'kOptionHideNetworkSetting' not in dsp, "网络页签 if 块未移除"
        assert '// SettingsTabKey.safety,  (hidden by custom build)' in dsp, "安全页签隐藏失败"
        assert '// SettingsTabKey.account,  (hidden by custom build)' in dsp, "账户页签隐藏失败"
        assert '// SettingsTabKey.printer,  (hidden by custom build)' in dsp, "打印机页签隐藏失败"

        cp = open(os.path.join(pages, "connection_page.dart"), encoding="utf-8").read()
        assert 'offstage: true,' in cp, "服务器输入框隐藏失败"
        assert '_svcStopped' not in cp, "_svcStopped 残留"

        hp = open(os.path.join(pages, "desktop_home_page.dart"), encoding="utf-8").read()
        assert 'buildIDBoard(context)' in hp, "主页面 ID 面板缺失"
        assert 'loadPowered' not in hp, "主页面 Powered by 未移除"
        assert 'loadLogo' not in hp, "主页面 Logo 未移除"
        assert 'buildTip' not in hp, "主页面提示未移除"
        assert 'buildHelpCards' not in hp, "主页面帮助卡片未移除"
        assert 'buildPluginEntry' not in hp, "主页面插件入口未移除"

        print("SELFTEST PASSED ✓  所有正则均命中当前源码结构，替换结果正确。")
        return True
    except AssertionError as e:
        print("SELFTEST FAILED ✗", e)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="RustDesk Windows 定制补丁")
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
    elif args.target == "rustdesk":
        patch_rustdesk(args.path, dry)
    elif args.target == "all":
        cmd_all(args.path, args.server, args.key, dry)
    print("\n完成。建议用 `git diff` 复查改动后再提交/编译。")


if __name__ == "__main__":
    main()
