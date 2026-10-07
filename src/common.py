# -*- coding: utf-8 -*-
"""
实验二《百万富翁问题与不经意传输》—— 公共基础模块
==================================================

本模块提供三部分公共能力：

1. ``Channel``          —— 模拟两方之间的通信信道，自动统计
                           **通信字节数** 与 **交互轮数（消息条数）**，
                           并完整记录每一条消息的方向与语义。
2. 基础数论与 RSA       —— Miller-Rabin 素性检测、随机大素数生成、
                           RSA 密钥对生成、模幂运算（带次数统计）。
                           全部基于 Python 标准库实现，不依赖第三方密码库。
3. ``mask`` / ``unmask`` —— 基于 SHA-256 的密钥流（MGF1 风格），
                           用于 OT 中对消息做定长一次性加密（异或掩码）。

作者：实验二
"""

from __future__ import annotations

import hashlib
import math
import secrets
import time
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# 全局计数器：统计模幂运算次数，用于分析"计算开销"
# ---------------------------------------------------------------------------


class _Counters:
    """轻量全局计数器。"""

    def __init__(self) -> None:
        self.modexp = 0          # 模幂次数
        self.modexp_bits = 0     # 模数比特长度累计（粗略衡量计算量）
        self.prime_retry = 0     # 素数/间距检验重试次数

    def reset(self) -> None:
        self.modexp = 0
        self.modexp_bits = 0
        self.prime_retry = 0


COUNTERS = _Counters()


def modexp(base: int, exp: int, mod: int) -> int:
    """带统计的模幂运算：base^exp mod mod。"""
    COUNTERS.modexp += 1
    COUNTERS.modexp_bits += mod.bit_length()
    return pow(base, exp, mod)


# ---------------------------------------------------------------------------
# 1. 可统计的模拟信道
# ---------------------------------------------------------------------------


class Channel:
    """
    两方通信信道。

    约定：调用 ``send(sender, receiver, payload, note)`` 即代表 sender 向
    receiver 发送了一条消息。信道会：
      * 按"序列化后的字节数"累加通信量；
      * 每发送一条消息记为一轮（一次单向传输）；
      * 记录一条可审计的日志（序号 / 发送方 / 接收方 / 语义说明 / 字节数）。
    """

    def __init__(self) -> None:
        self.bytes = 0
        self.rounds = 0
        self.log: List[Dict[str, Any]] = []

    # -- 核心发送接口 --------------------------------------------------
    def send(self, sender: str, receiver: str, payload: Any, note: str = "") -> Any:
        """发送一条消息，返回 payload 本身（便于链式书写）。"""
        size = wire_size(payload)
        self.bytes += size
        self.rounds += 1
        self.log.append(
            {
                "seq": self.rounds,
                "from": sender,
                "to": receiver,
                "note": note,
                "bytes": size,
            }
        )
        return payload

    def reset(self) -> None:
        self.bytes = 0
        self.rounds = 0
        self.log.clear()

    def summary(self) -> str:
        lines = [f"  总轮数 = {self.rounds} 条消息，总字节数 = {self.bytes} B"]
        for rec in self.log:
            lines.append(
                f"    [{rec['seq']:>2}] {rec['from']:<6} -> {rec['to']:<6} "
                f"{rec['bytes']:>8} B   {rec['note']}"
            )
        return "\n".join(lines)


def wire_size(obj: Any) -> int:
    """
    估算对象在网络上传输所占的字节数。

      * int   : ceil(bit_length / 8)，至少 1 字节（定长大整数编码）
      * bytes : 实际长度
      * str   : UTF-8 编码后的长度
      * list/tuple/set : 各元素之和
      * dict  : 键与值之和
    """
    if isinstance(obj, bool):
        return 1
    if isinstance(obj, int):
        return max(1, (obj.bit_length() + 7) // 8)
    if isinstance(obj, bytes):
        return len(obj)
    if isinstance(obj, str):
        return len(obj.encode("utf-8"))
    if isinstance(obj, (list, tuple, set)):
        return sum(wire_size(x) for x in obj)
    if isinstance(obj, dict):
        return sum(wire_size(k) + wire_size(v) for k, v in obj.items())
    raise TypeError(f"不支持的负载类型: {type(obj)}")


# ---------------------------------------------------------------------------
# 2. 基础数论：素性检测、随机素数、RSA 密钥生成
# ---------------------------------------------------------------------------

_SMALL_PRIMES = [
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67,
    71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149,
    151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199, 211, 223, 227, 229,
]

_rng = secrets.SystemRandom()


def is_probable_prime(n: int, rounds: int = 40) -> bool:
    """Miller-Rabin 概率素性检测（rounds 越大误判概率越低，默认误判 < 2^-80）。"""
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n == p:
            return True
        if n % p == 0:
            return False
    # 写成 n - 1 = d * 2^s
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = _rng.randrange(2, n - 1)
        x = modexp(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def gen_prime(bits: int) -> int:
    """生成一个 bit_length 恰为 bits 的随机（概率）素数。"""
    while True:
        cand = _rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(cand):
            return cand


class RSAKey:
    """极简 RSA 密钥对容器。"""

    __slots__ = ("n", "e", "d", "bits")

    def __init__(self, n: int, e: int, d: int, bits: int) -> None:
        self.n = n
        self.e = e
        self.d = d
        self.bits = bits

    def __repr__(self) -> str:  # pragma: no cover
        return f"RSAKey(bits={self.bits}, n={self.n >> (self.bits - 32)}...)"


def gen_rsa_keypair(bits: int, e: int = 65537) -> RSAKey:
    """
    生成 bits 位的 RSA 密钥对。

    步骤：随机生成两个 bits/2 位的大素数 p、q -> n = p*q ->
    phi = (p-1)(q-1) -> 要求 gcd(e, phi) = 1 -> d = e^{-1} mod phi。
    """
    if bits < 256:
        raise ValueError("RSA 模数至少需要 256 比特")
    while True:
        p = gen_prime(bits // 2)
        q = gen_prime(bits // 2)
        if p == q:
            continue
        n = p * q
        phi = (p - 1) * (q - 1)
        if math.gcd(e, phi) != 1:
            continue
        d = pow(e, -1, phi)
        return RSAKey(n, e, d, bits)


def rand_int(bits: int) -> int:
    """返回 [0, 2^bits) 内的密码学安全随机整数。"""
    return _rng.getrandbits(bits)


def rand_below(n: int) -> int:
    """返回 [1, n-1] 内的随机整数（几乎必然与 n 互素）。"""
    return _rng.randrange(1, n)


# ---------------------------------------------------------------------------
# 3. 基于 SHA-256 的密钥流掩码（OT 消息的一次性加密）
# ---------------------------------------------------------------------------

_MASK_DOMAIN = b"LAB2-OT-MASK-v1"


def keystream(seed: bytes, length: int) -> bytes:
    """MGF1 风格密钥流：SHA256(seed || counter) 级联。"""
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(_MASK_DOMAIN + seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(out[:length])


def int_to_seed(x: int) -> bytes:
    """把大整数规范地序列化成掩码种子（保证双方得到完全相同的字节串）。"""
    length = max(1, (x.bit_length() + 7) // 8)
    return x.to_bytes(length, "big")


def mask(msg: bytes, seed_int: int) -> bytes:
    """用 seed_int 派生的密钥流对 msg 做异或加密（要求 len 固定）。"""
    ks = keystream(int_to_seed(seed_int), len(msg))
    return bytes(a ^ b for a, b in zip(msg, ks))


unmask = mask  # 异或是对合运算，加解密同函数


# ---------------------------------------------------------------------------
# 4. 结果常量与辅助
# ---------------------------------------------------------------------------

MSG_ALICE_RICHER = "Alice 更富有"
MSG_BOB_RICHER = "Bob 更富有"
MSG_EQUAL = "双方财富相等"

MESSAGE_BLOCK = 32  # OT 中消息的定长块长度（字节），避免长度侧信道


def pad_block(text: str, size: int = MESSAGE_BLOCK) -> bytes:
    """把结果字符串填充为定长块，防止通过长度泄露信息。"""
    raw = text.encode("utf-8")
    if len(raw) > size:
        raise ValueError(f"消息过长: {len(raw)} > {size}")
    return raw + b"\x00" * (size - len(raw))


def unpad_block(block: bytes) -> str:
    return block.rstrip(b"\x00").decode("utf-8", errors="replace")


def ground_truth(a: int, b: int) -> str:
    """明文参考结果（仅用于测试校验，协议内部绝不使用）。"""
    if a > b:
        return MSG_ALICE_RICHER
    if a < b:
        return MSG_BOB_RICHER
    return MSG_EQUAL


class Timer:
    """简易计时上下文。"""

    def __init__(self) -> None:
        self.elapsed = 0.0

    def __enter__(self) -> "Timer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.elapsed = time.perf_counter() - self._t0
