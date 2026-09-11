#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用内核树内自带的 android/abi_gki_aarch64.xml 校验给定 vmlinux.symvers。"""
import sys, os, xml.etree.ElementTree as ET

def load_reference(path):
    root = ET.parse(path).getroot()
    ref = {}
    for node in root.iter():
        if node.tag in ("elf-function-symbols", "elf-variable-symbols"):
            for s in node.findall("elf-symbol"):
                crc = s.get("crc")
                if crc:
                    ref[s.get("name")] = int(crc, 16)
    return ref

def load_symvers(path):
    d = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        f = line.split()
        if len(f) >= 2:
            try:
                d[f[1]] = int(f[0], 16)
            except ValueError:
                pass
    return d

def main():
    if len(sys.argv) < 3:
        print("用法: %s <abi_gki_aarch64.xml> <vmlinux.symvers> [label]" % sys.argv[0])
        return 2
    xml, symvers = sys.argv[1], sys.argv[2]
    label = sys.argv[3] if len(sys.argv) > 3 else "kernel"
    ref = load_reference(xml)
    sym = load_symvers(symvers)
    common = set(ref) & set(sym)
    bad = sorted(k for k in common if ref[k] != sym[k])
    missing = sorted(set(ref) - set(sym))

    print("== GKI ABI 基线校验 — %s ==" % label)
    print("基线符号数        : %d" % len(ref))
    print("镜像导出符号数    : %d" % len(sym))
    print("参与比对          : %d" % len(common))
    print("CRC 不一致        : %d" % len(bad))
    print("基线有/镜像无     : %d" % len(missing))
    if bad:
        print("---- CRC 不一致明细 ----")
        for k in bad:
            print("  %-46s 基线=0x%08x 镜像=0x%08x" % (k, ref[k], sym[k]))
    if missing:
        print("---- 缺失符号明细（原厂内核同样缺失，不阻塞） ----")
        for k in missing:
            print("  %s" % k)
    if bad:
        print("GKI_ABI_CHECK_FAIL")
        return 1
    print("GKI_ABI_CHECK_OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
