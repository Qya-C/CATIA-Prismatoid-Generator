# -*- coding: utf-8 -*-
"""
diagnose_v2.py
==============
命令行版能力自检（2.0）。

四段结构
〇、版本与路径自检
一、方法签名探测
二、主能力自检（数学自检 + 1.0 回归 + 2.0 新增）
三、点截面探查（探测性，不计入通过率）

运行：python diagnose_v2.py
注意：会在 CATIA 中新建并关闭若干空 Part 文档（不保存）。
"""

from __future__ import annotations

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# 2.0 基线：主自检应通过的用例数
#   底层 3 + 数学自检 1 + 1.0 六种图形回归 6 + 2.0 新增 12 = 22
#   注意：本值必须等于内核 _CASES 的用例数（下面会动态校验）。
#
#   历史：1.0 时代本值为 20；2.0 内核新增『★斜棱锥』与『★拒绝·非共面却要实体』
#   两例后未同步，导致 k=0 棱锥的回归失败被这个过期基线掩盖
#   （20 != 22 虽已报警，但文案只说"与基线不符"，容易被当成噪声忽略）。
BASELINE_PASS_COUNT = 22

CONTROLLER_MODULE = "catia_controller_v2"


def _module_dir_of(mod) -> str:
    d = getattr(mod, "MODULE_DIR", None)
    if d:
        return str(d)
    f = getattr(mod, "__file__", None)
    return os.path.dirname(os.path.abspath(f)) if f else ""


def main() -> int:
    print("=" * 84)
    print("〇、版本与路径自检")
    print("=" * 84)

    try:
        import importlib
        cc = importlib.import_module(CONTROLLER_MODULE)
    except Exception as exc:
        print(f"  无法导入 {CONTROLLER_MODULE}：{exc}")
        print("  请确认内核文件名与 CONTROLLER_MODULE 一致，且与本脚本同目录。")
        return 2

    try:
        print(cc.version_info())
    except Exception as exc:
        print(f"  version_info() 调用失败：{exc}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    mod_dir = _module_dir_of(cc)
    print(f"  内核模块名：{CONTROLLER_MODULE}")
    print(f"  本脚本文件：{os.path.abspath(__file__)}")
    print()

    if not mod_dir:
        print("  ⚠ 无法确定内核所在目录，跳过同目录检查。")
    elif os.path.normcase(script_dir) != os.path.normcase(mod_dir):
        print("  ⚠ 警告：本脚本与内核不在同一目录！")
        print(f"     脚本目录：{script_dir}")
        print(f"     内核目录：{mod_dir}")
        print("     存在多份代码副本的风险。可用以下命令列出所有副本：")
        print(r'       Get-ChildItem -Recurse -Filter *.py | '
              r'Select-Object FullName, LastWriteTime | Format-Table -AutoSize')
    else:
        print("  ✓ 本脚本与内核位于同一目录，代码来源一致。")
    print()

    print("=" * 84)
    print("一、方法签名探测（本机实测）")
    print("=" * 84)
    try:
        print(cc.dump_signatures())
    except Exception as exc:
        print(f"  失败：{exc}")

    print()
    print("=" * 84)
    print("二、主能力自检（每例一个全新空 Part）")
    print("=" * 84)

    try:
        results, conclusion = cc.run_diagnostics()
    except Exception as exc:
        print(f"  自检过程异常：{exc}")
        return 2

    for idx, r in enumerate(results, start=1):
        mark = "✓ 通过" if r["ok"] else "✗ 失败"
        print(f"[{idx:>2}/{len(results)}] {r['case']:<40} {mark}")
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
    total = len(results)
    bad = []

    if total != BASELINE_PASS_COUNT:
        bad.append(f"用例总数 {total} 与基线 {BASELINE_PASS_COUNT} 不一致"
                   "（内核用例表被改动，请同步 BASELINE_PASS_COUNT）")
    if passed != total:
        failed = [r["case"] for r in results if not r["ok"]]
        bad.append(f"{total - passed} 个用例失败：" + "、".join(failed))

    if bad:
        print("=" * 84)
        print("⚠ 未达 2.0 基线")
        print("=" * 84)
        print(f"  基线要求：{BASELINE_PASS_COUNT}/{BASELINE_PASS_COUNT} 全部通过")
        print(f"  本次实际：{passed}/{total} 通过")
        for b in bad:
            print(f"  · {b}")
        print()
    else:
        print(f"  ✓ 与 2.0 基线一致（{passed}/{total} 全部通过）。")
        print()

    print("=" * 84)
    print("三、点截面探查（探测性，不计入通过率）")
    print("=" * 84)
    try:
        ok, text = cc.probe_point_section()
        print(text)
    except Exception as exc:
        print(f"  探查过程异常：{exc}")

    print()
    print("=" * 84)
    print("四、2.0 使用要点")
    print("=" * 84)
    print("  1) 斜拟柱体：把『错位 pu/pv』设成非零即可。")
    print("     此时侧面仍是平面梯形，可正常出实体。倾斜角 = atan(|p| / h)。")
    print("  2) 扭转角 β≠0、或给出独立顶面轮廓、或各向异性缩放，")
    print("     都会让侧面失去共面性（变成双曲抛物面），只能输出曲面。")
    print("     程序会自动检出非共面面号并报告，不会静默产出错误几何。")
    print("  3) 任意基准面：三种定义方式任选；三点法会自动构造右手正交基。")
    print("  4) 任意多边形：顶点表支持直角坐标与极坐标，")
    print("     程序自动统一绕向为逆时针，并检查自交与重合顶点。")
    print()
    print("  建议目视复核：")
    print("    · n=6 / k=0.5 / offset 非零 → 六个侧面是否都是平面梯形")
    print("    · 任意平面（三点确定）+ 星形轮廓 → 实体是否贴合该平面")
    return 0


if __name__ == "__main__":
    sys.exit(main())
