# -*- coding: utf-8 -*-
"""
diagnose_v1.py
==============
命令行版能力自检，与界面『能力自检』共用同一套实现。

版本：1.0.0（2026.09.20 冻结）· 内部标识 2026.09.20-r6
基线：主自检 11/11 通过；点截面探查 2/2 不可用（预期）。

四段结构
--------
〇、版本与路径自检 —— 确认运行的是哪一份代码（防止多副本误跑）
一、方法签名探测   —— 打印本机实际可用的 API 签名
二、主能力自检     —— 11 个用例，全部应当通过
三、点截面探查     —— 探测性，不计入通过率

运行：python diagnose_v1.py
注意：会在 CATIA 中新建并关闭若干空 Part 文档（不保存），
      请先保存手头正在编辑的文档。
"""

from __future__ import annotations

import os
import sys

# ---- 输出编码兜底：避免中文在 Windows 终端乱码 ----
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# 1.0.0 冻结基线：主自检应通过的用例数。
# 若实际结果与该值不符，说明代码或环境已偏离冻结基线，必须查明原因。
EXPECTED_PASS_COUNT = 11

# 内核模块名（与文件名一致）。改名时只需改这一处。
CONTROLLER_MODULE = "catia_controller_v1"


def _module_dir_of(mod) -> str:
    """尽最大努力取出模块所在目录；取不到返回空串。

    存在的意义：即使内核缺少 MODULE_DIR 属性，
    本脚本也应降级提示，而不是直接抛 AttributeError 崩掉。
    """
    d = getattr(mod, "MODULE_DIR", None)
    if d:
        return str(d)
    f = getattr(mod, "__file__", None)
    if f:
        return os.path.dirname(os.path.abspath(f))
    return ""


def main() -> int:
    # ============================================================
    # 〇、版本与路径自检
    # ============================================================
    print("=" * 84)
    print("〇、版本与路径自检（第一步务必核对本节）")
    print("=" * 84)

    try:
        import importlib
        cc = importlib.import_module(CONTROLLER_MODULE)
    except Exception as exc:
        print(f"  无法导入 {CONTROLLER_MODULE}：{exc}")
        print("  请确认：内核文件名与 CONTROLLER_MODULE 一致，且与本脚本同目录。")
        return 2

    try:
        print(cc.version_info())
    except AttributeError as exc:
        print(f"  ⚠ 本内核缺少 version_info()：{exc}")
        print(f"    内核文件：{getattr(cc, '__file__', '未知')}")
    except Exception as exc:
        print(f"  version_info() 调用失败：{exc}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    mod_dir = _module_dir_of(cc)
    print(f"  内核模块名：{CONTROLLER_MODULE}")
    print(f"  本脚本文件：{os.path.abspath(__file__)}")
    print()

    if not mod_dir:
        print("  ⚠ 无法确定内核所在目录，跳过同目录检查。")
        print(f"     内核模块：{getattr(cc, '__file__', '未知')}")
        print()
    elif os.path.normcase(script_dir) != os.path.normcase(mod_dir):
        print("  ⚠ 警告：本脚本与内核不在同一目录！")
        print(f"     脚本目录：{script_dir}")
        print(f"     内核目录：{mod_dir}")
        print("     存在多份代码副本的风险，请确认运行的是最新那一份。")
        print("     可执行以下命令列出所有副本：")
        print(r'       Get-ChildItem -Recurse -Filter *.py | '
              r'Select-Object FullName, LastWriteTime | Format-Table -AutoSize')
        print()
    else:
        print("  ✓ 本脚本与内核位于同一目录，代码来源一致。")
        print()

    # ============================================================
    # 一、方法签名探测
    # ============================================================
    print("=" * 84)
    print("一、方法签名探测（本机实测）")
    print("=" * 84)
    try:
        print(cc.dump_signatures())
    except Exception as exc:
        print(f"  失败：{exc}")

    # ============================================================
    # 二、主能力自检
    # ============================================================
    print()
    print("=" * 84)
    print("二、主能力自检（每个用例一个全新空 Part；全部应当通过）")
    print("=" * 84)

    try:
        results, conclusion = cc.run_diagnostics()
    except Exception as exc:
        print(f"  自检过程异常：{exc}")
        return 2

    for idx, r in enumerate(results, start=1):
        mark = "✓ 通过" if r["ok"] else "✗ 失败"
        print(f"[{idx:>2}/{len(results)}] {r['case']:<32} {mark}")
        for stage, ok, msg in r["rows"]:
            print(f"            {'✓' if ok else '✗'} {stage}")
            if msg:
                print(f"              {msg}")
        for d in r.get("diag", []):
            for line in str(d).splitlines():
                print(f"            · {line}")
        print()

    print("=" * 84)
    print("二之结论")
    print("=" * 84)
    print(conclusion)

    passed = sum(1 for r in results if r["ok"])
    if passed != EXPECTED_PASS_COUNT:
        print("=" * 84)
        print("⚠ 偏离冻结基线")
        print("=" * 84)
        print(f"  1.0.0 基线：{EXPECTED_PASS_COUNT}/{EXPECTED_PASS_COUNT} 通过")
        print(f"  本次实际　：{passed}/{len(results)} 通过")
        print("  请勿在此状态下继续开发：先查明偏离原因。")
        print()
    else:
        print(f"  ✓ 与 1.0.0 冻结基线一致（{EXPECTED_PASS_COUNT}/{EXPECTED_PASS_COUNT}）。")
        print()

    # ============================================================
    # 三、点截面探查（不计入通过率）
    # ============================================================
    print("=" * 84)
    print("三、点截面探查（探测性，不计入通过率；不可用属 1.0.0 预期）")
    print("=" * 84)
    try:
        ok, text = cc.probe_point_section()
        print(text)
    except Exception as exc:
        print(f"  探查过程异常：{exc}")

    # ============================================================
    # 四、判读指引
    # ============================================================
    print()
    print("=" * 84)
    print("四、判读指引")
    print("=" * 84)
    print("  · 第〇节：关键常量应与最新代码一致；")
    print("           若提示“不在同一目录”，说明存在多份副本，务必清理。")
    print(f"  · 第二节应恰为 {EXPECTED_PASS_COUNT} 项全通过 —— 这是 1.0.0 的冻结基线。")
    print("  · 第三节不可用属预期，已记录为 1.0.0 已知限制：")
    print("      k=0 的锥体使用极小顶面近似（误差约 0.1%，肉眼不可见）。")
    print()
    print("  1.0.0 遗留的人工复核项（不影响功能性验收，但建议确认）：")
    print("    1) n=6, k=0.5 的棱台侧面有无扭曲（验证耦合方式=4 是否正确）")
    print("    2) k=0 的圆锥顶部是否收敛成一个点（不满意就调小 CONE_TOP_EPS_REL）")
    return 0


if __name__ == "__main__":
    sys.exit(main())