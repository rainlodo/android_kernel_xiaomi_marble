#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
#
# 生成 GlowR 内核的版本串（写进 .config 的 CONFIG_LOCALVERSION）。
#
# 最终 uname -r 形如：
#   5.10.238-GlowR-v1.0.10-20260912-1843-g29a0a3b63
#   └─ KERNELVERSION ─┘└── 本脚本写入 ──┘└ scm 版本(setlocalversion) ┘
#
# 用法: scripts/glowr-version.sh <O=构建目录> [版本号] [编译时间戳]
#   scripts/glowr-version.sh out v1.0.10 20260912-1843
#   scripts/glowr-version.sh out          # 版本号取最近 GlowR tag，时间戳取当前时间
#
# 注意：CONFIG_LOCALVERSION 只是版本串的显示名，不参与任何符号 CRC 计算
#       （模块带 CRC 时内核只比较 vermagic 里第一个空格之后的部分），
#       所以改它不会影响与原厂模块的 ABI 一致性。

set -e

O="${1:-out}"
VER="${2:-}"
STAMP="${3:-}"

if [ ! -f "$O/.config" ]; then
	echo "错误: 找不到 $O/.config，请先执行 make <defconfig>" >&2
	exit 1
fi

if [ -z "$VER" ]; then
	VER="$(git describe --tags --match 'GlowR-v*' --abbrev=0 2>/dev/null | sed 's/^GlowR-//' || true)"
fi
[ -n "$VER" ] || VER=dev

if [ -z "$STAMP" ]; then
	STAMP="$(TZ=Asia/Shanghai date +%Y%m%d-%H%M)"
fi

LOCAL="-GlowR-${VER}-${STAMP}"
scripts/config --file "$O/.config" --set-str LOCALVERSION "$LOCAL"
echo "CONFIG_LOCALVERSION=\"$LOCAL\""
