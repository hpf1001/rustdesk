#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RustDesk Windows 定制补丁脚本（跨平台，Python 3.8+）
=====================================================
作用：
  1. 把自建 ID/中继服务器地址和公钥 KEY 烧进源码（hbb_common/src/config.rs）
  2. 锁死 KEY，使客户端不使用用户在“设置-网络”里填写的 key（始终用内置 RS_PUB_KEY）
  3. 精简界面：
       - 隐藏“设置”里的“网络”页签（不再能改服务器/key）
       - 隐藏主界面上的“ID/中继服务器”输入框

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
import argparse
import tempfile
import shutil


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
    if not edits:
        print("  [INFO] 未提供 --server/--key，跳过 config.rs 写入")
        return
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

    # 2) 隐藏“设置 - 网络”页签（服务器/key 入口）
    #    注意：network 项被一个 `if (...) {}` 包裹，只注释该项会留下悬空 if 导致编译失败，
    #    因此连同整个 if 块一起注释掉。
    dsp = os.path.join(root, "flutter", "lib", "desktop", "pages", "desktop_setting_page.dart")
    patch_file(dsp, [(
        re.compile(
            r"if \(!bind\.isDisableSettings\(\) &&\s*\n\s*"
            r"bind\.mainGetBuildinOption\(key: kOptionHideNetworkSetting\) != 'Y'\)\s*\n\s*"
            r"SettingsTabKey\.network,",
            re.DOTALL,
        ),
        '// SettingsTabKey.network,  (hidden by custom build)',
    )], dry)

    # 3) 隐藏主界面的“ID/中继服务器”输入框（setupServerWidget）
    cp = os.path.join(root, "flutter", "lib", "desktop", "pages", "connection_page.dart")
    patch_file(cp, [(
        re.compile(r'offstage:\s*!\(!_svcStopped.*?\),', re.DOTALL),
        'offstage: true,',
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
                '    if (!bind.isIncomingOnly()) SettingsTabKey.display,\n'
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

        cp = open(os.path.join(pages, "connection_page.dart"), encoding="utf-8").read()
        assert 'offstage: true,' in cp, "服务器输入框隐藏失败"
        assert '_svcStopped' not in cp, "_svcStopped 残留"

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
