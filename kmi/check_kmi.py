#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KMI / ABI 对账工具（GlowR kernel for Redmi Note 12 Turbo / marble）

用法:
    python3 kmi/check_kmi.py --symvers out/Module.symvers \
                             --reference kmi/abi_reference.tsv \
                             [--report kmi_report.txt] [--max-list 40]

为什么需要它:
  ROM 里的 316 个 vendor 模块（/vendor_dlkm/lib/modules，只读分区）带 __versions 段，
  内核加载时会用 check_version() 逐个符号比对 CRC。只要有一个符号对不上，就会打印
  "disagrees about version of symbol xxx" 并拒绝加载该模块。
  原版 Melt 内核为了强行加载，把 check_version() 改成了 return 1（打印 but ignore），
  于是 30% 的符号 CRC 不一致也照样加载 -> 结构体布局不匹配 -> 随机踩内存死机。
  正确做法是让内核导出的符号 CRC 与原厂内核完全一致，然后用本脚本证明它。

数据格式:
  符号表每行:  CRC(hex) \t symbol \t module \t export
      这是本次构建「内核导出给模块的符号 + 其 CRC」，和模块加载时比对的是同一份数据。
      也兼容 2 列格式 (CRC(hex) \t symbol)，便于拿原厂内核导出的符号表做自检。
  kmi/abi_reference.tsv 每行: CRC \t symbol \t vmlinux|MODULE \t REQUIRED|kernel|MODULE
      vmlinux/REQUIRED : 原厂 ROM 模块真正需要、且原厂内核导出的符号 -> 必须逐条一致
      vmlinux/kernel   : 原厂内核导出、但 ROM 模块没引用的符号 -> 仅供参考
      MODULE/*         : ROM 模块之间互相引用的符号（由 ROM 自己的模块提供）-> 无需关心

退出码:
  0 = REQUIRED 全部一致
  1 = 存在 CRC 不一致或缺失（不可刷机）
  2 = 输入文件缺失/格式错误
"""

import argparse
import collections
import os
import sys

EXPECT_MODULE_LAYOUT = 0x7C24B32D  # 原厂 module_layout CRC（struct module 布局指纹）


def parse_symvers(path):
    """返回 {name: (crc, module)}"""
    out = {}
    with open(path, "r", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            try:
                crc = int(parts[0], 16) & 0xFFFFFFFF
            except ValueError:
                continue
            name = parts[1]
            mod = parts[2] if len(parts) > 2 else "vmlinux"
            out[name] = (crc, mod)
    return out


def parse_reference(path):
    """返回 (required, optional, module_count)"""
    required, optional, n_module = [], [], 0
    with open(path, "r", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4:
                continue
            try:
                crc = int(p[0], 16) & 0xFFFFFFFF
            except ValueError:
                continue
            name, kind, role = p[1], p[2], p[3]
            if kind == "vmlinux" and role == "REQUIRED":
                required.append((crc, name))
            elif kind == "vmlinux":
                optional.append((crc, name))
            else:
                n_module += 1
    return required, optional, n_module


def group_by_prefix(names):
    cnt = collections.Counter()
    for n in names:
        head = n.split("_", 1)[0] if "_" in n else "(other)"
        cnt[head] += 1
    return cnt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symvers", required=True, help="本次构建 out/Module.symvers")
    ap.add_argument("--reference", required=True, help="kmi/abi_reference.tsv")
    ap.add_argument("--report", default=None, help="把报告写入该文件")
    ap.add_argument("--label", default="", help="本次构建的标签（如 variant 名）")
    ap.add_argument("--max-list", type=int, default=40, help="明细最多打印多少条")
    args = ap.parse_args()

    for p in (args.symvers, args.reference):
        msg = None
        if not os.path.exists(p):
            msg = "找不到文件 %s" % p
        elif os.path.getsize(p) == 0:
            msg = "文件为空 %s（构建没产出符号表？）" % p
        if msg:
            text = ("================ KMI / ABI 对账报告 ================\n"
                    "ERROR: %s\n"
                    "===================================================\n" % msg)
            sys.stderr.write(text)
            if args.report:
                with open(args.report, "w", encoding="utf-8") as f:
                    f.write(text)
            return 2

    built = parse_symvers(args.symvers)
    required, optional, n_module = parse_reference(args.reference)

    lines = []
    def emit(s=""):
        lines.append(s)

    emit("================ KMI / ABI 对账报告 ================")
    if args.label:
        emit("构建标签        : %s" % args.label)
    emit("Module.symvers  : %s（%d 个导出符号）" % (args.symvers, len(built)))
    emit("参考基线        : %s" % args.reference)
    emit("                : REQUIRED %d / 参考 kernel %d / ROM 模块间符号 %d"
         % (len(required), len(optional), n_module))
    emit("")

    # ---- 1. module_layout：最关键的一行 ----
    ml = built.get("module_layout", (None, None))[0]
    ml_ref = {name: crc for crc, name in required}.get("module_layout")
    emit("---- 1) module_layout（struct module 布局指纹）----")
    if ml is None:
        emit("  ✗ 本次构建没有导出 module_layout（异常）")
    else:
        ok = (ml_ref is not None and ml == ml_ref)
        emit("  本次构建 : 0x%08x" % ml)
        emit("  原厂期望 : %s" % ("0x%08x" % ml_ref if ml_ref is not None else "(不在基线里)"))
        emit("  结论     : %s" % ("一致 ✓" if ok else "不一致 ✗"))
    emit("")

    # ---- 2. REQUIRED 逐条比对 ----
    ok_n = 0
    mismatched, missing = [], []
    for ref_crc, name in required:
        got = built.get(name)
        if got is None:
            missing.append((ref_crc, name))
        elif got[0] != ref_crc:
            mismatched.append((ref_crc, got[0], name))
        else:
            ok_n += 1

    emit("---- 2) REQUIRED（ROM vendor 模块必需，必须全部一致）----")
    emit("  一致     : %d / %d" % (ok_n, len(required)))
    emit("  CRC 不一致: %d" % len(mismatched))
    emit("  缺失     : %d" % len(missing))
    if mismatched:
        emit("")
        emit("  按前缀归类: " + ", ".join("%s %d" % kv for kv in group_by_prefix([x[2] for x in mismatched]).most_common(15)))
        emit("  明细（最多 %d 条: 符号 期望CRC 本次CRC）:" % args.max_list)
        for ref_crc, got_crc, name in mismatched[: args.max_list]:
            emit("    %-48s 0x%08x 0x%08x" % (name, ref_crc, got_crc))
        if len(mismatched) > args.max_list:
            emit("    ...（还有 %d 条）" % (len(mismatched) - args.max_list))
    if missing:
        emit("")
        emit("  按前缀归类: " + ", ".join("%s %d" % kv for kv in group_by_prefix([x[1] for x in missing]).most_common(15)))
        emit("  明细（最多 %d 条: 符号 期望CRC）:" % args.max_list)
        for ref_crc, name in missing[: args.max_list]:
            emit("    %-48s 0x%08x" % (name, ref_crc))
        if len(missing) > args.max_list:
            emit("    ...（还有 %d 条）" % (len(missing) - args.max_list))
    emit("")

    # ---- 3. 参考 kernel 符号（非必需，仅供诊断）----
    opt_ok = opt_mis = opt_missing = 0
    opt_mis_names = []
    for ref_crc, name in optional:
        got = built.get(name)
        if got is None:
            opt_missing += 1
        elif got[0] != ref_crc:
            opt_mis += 1
            opt_mis_names.append(name)
        else:
            opt_ok += 1
    emit("---- 3) 参考 kernel 符号（ROM 模块未引用，仅供参考）----")
    emit("  一致 %d / CRC 不一致 %d / 缺失 %d" % (opt_ok, opt_mis, opt_missing))
    if opt_mis_names:
        emit("  不一致示例: " + ", ".join(opt_mis_names[:10]))
    emit("")

    passed = (not mismatched) and (not missing) and (ml == ml_ref if ml_ref is not None else True)
    emit("---- 结论 ----")
    if passed:
        emit("  ✓ 通过：REQUIRED 全部一致，模块加载不会再出现 disagrees about version of symbol")
        emit("    刷机命令（fastboot，先确认当前槽位）:")
        emit("      fastboot flash boot <GlowR-kernel-marble-*.zip 解出来的 boot.img>  # 或用内核管理器刷 zip")
        emit("    刷完自检:")
        emit("      adb shell su -c 'dmesg | grep -c \"disagrees about version\"'   # 必须为 0")
        emit("      adb shell su -c 'cat /proc/sys/kernel/tainted'                 # 原厂/干净内核应为 0")
    else:
        emit("  ✗ 不通过：%d 个符号 CRC 不一致、%d 个符号缺失 -> 不能刷机" % (len(mismatched), len(missing)))
        if mismatched:
            emit("    含义: 这些符号涉及的结构体/类型布局仍与原厂内核不同（多半是 defconfig 又引入了新差异）")
        if missing:
            emit("    含义: 内核根本没导出这些符号（多半是某个 CONFIG_ 关了，对应的驱动/功能被裁掉了）")
    emit("===================================================")

    text = "\n".join(lines)
    print(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())