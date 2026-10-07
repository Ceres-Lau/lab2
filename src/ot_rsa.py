# -*- coding: utf-8 -*-
"""
任务二（上半）：n 选 1 不经意传输（1-out-of-n Oblivious Transfer）
==================================================================

采用的协议
----------
基于 **RSA 的 Even–Goldreich–Lempel（EGL）构造** 推广到 n 条消息。
公共参数：RSA 模数 n（|n| = bits 比特），公钥指数 e = 65537。

设发送方 S 持有 m_0, ..., m_{n-1}，接收方 R 持有选择 σ ∈ {0,...,n-1}。

**第 1 轮  S → R**
    S 生成 RSA 密钥对 (N, e, d)，并独立随机选取 n 个盲化因子
    x_0, ..., x_{n-1} ∈ Z_N^*；发送 (N, e, x_0..x_{n-1})。

**第 2 轮  R → S**
    R 随机选 k ∈ Z_N^*，计算

        y = x_σ · k^e mod N

    发送 y。由于 k^e 是一个随机的 e 次幂，y 在 Z_N^* 上（在 RSA 假设下）
    与"均匀分布"不可区分，因此 **S 无法判断 σ**——接收方选择被保护。

**第 3 轮  S → R**
    S 对每一个 i 计算

        k_i = (y · x_i^{-1})^d mod N
        c_i = m_i ⊕ H(k_i)                 （H 为 SHA-256 派生的密钥流）

    发送 c_0..c_{n-1}。注意当 i = σ 时

        k_σ = (x_σ k^e x_σ^{-1})^d = (k^e)^d = k mod N

    而 i ≠ σ 时 k_i 是一个 R 无法预测的伪随机值（要求出它等价于求 e 次根，
    即攻破 RSA）。因此 **R 只能解开 m_σ**，其余消息仍是乱码——发送方消息被保护。

**第 4 步  R 本地解密**
    m_σ = c_σ ⊕ H(k)。

安全直觉
--------
* 发送方视角：看到的只是一个随机 e 次幂的陪集元素 y，对 σ 无任何信息
  （RSA 假设 + x_i 的随机性）。
* 接收方视角：要对 i ≠ σ 解密必须算出 k_i，即由 k_i^e = y/x_i 求 e 次根，
  这正是 RSA 求逆问题。
* 本实验按**半诚实模型**讨论：双方遵守协议，但会尽量从收到的消息中分析。

实现细节
--------
* 消息统一填充为定长 32 字节块（``MESSAGE_BLOCK``），避免长度侧信道；
* 掩码使用 SHA-256 的 MGF1 风格密钥流，保证定长异或的一次性语义；
* 模逆使用扩展欧几里得（Python 3.8+ 的 ``pow(a, -1, N)``）。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from common import (
    COUNTERS,
    Channel,
    MESSAGE_BLOCK,
    RSAKey,
    gen_rsa_keypair,
    mask,
    modexp,
    rand_below,
    unmask,
    unpad_block,
)


class OTSender:
    """发送方 S：持有 n 条消息，协议结束后**不应**得知接收方的选择 σ。"""

    def __init__(self, name: str, messages: Sequence[bytes],
                 key: Optional[RSAKey] = None, bits: int = 1024) -> None:
        self.name = name
        self.messages = [bytes(m) for m in messages]
        self.n_msg = len(self.messages)
        self.key = key if key is not None else gen_rsa_keypair(bits)
        self.xs: List[int] = []

    # 第 1 轮
    def round1(self, ch: Channel, peer: str):
        N, e = self.key.n, self.key.e
        self.xs = [rand_below(N) for _ in range(self.n_msg)]
        ch.send(
            self.name, peer, (N, e, self.xs),
            f"OT 第1轮  公钥 (N,e) 与 n={self.n_msg} 个盲化因子 x_i",
        )
        return N, e, self.xs

    # 第 3 轮
    def round3(self, ch: Channel, peer: str, y: int) -> List[bytes]:
        N, d = self.key.n, self.key.d
        ciphers: List[bytes] = []
        for i in range(self.n_msg):
            # k_i = (y / x_i)^d mod N —— n 次私钥模幂，是本方案主要计算开销
            k_i = modexp(y * pow(self.xs[i], -1, N) % N, d, N)
            ciphers.append(mask(self.messages[i], k_i))
        ch.send(
            self.name, peer, ciphers,
            f"OT 第3轮  n={self.n_msg} 条加密消息 c_i = m_i ⊕ H(k_i)",
        )
        return ciphers


class OTReceiver:
    """接收方 R：持有选择 σ，协议结束后**不应**得知未选中的消息。"""

    def __init__(self, name: str, sigma: int) -> None:
        self.name = name
        self.sigma = sigma          # 私有输入：选择索引
        self.k: Optional[int] = None

    # 第 2 轮
    def round2(self, ch: Channel, peer: str, N: int, e: int,
               xs: Sequence[int]) -> int:
        k = rand_below(N)
        self.k = k
        y = xs[self.sigma] * modexp(k, e, N) % N
        ch.send(
            self.name, peer, y,
            "OT 第2轮  y = x_σ · k^e mod N（选择被随机 e 次幂盲化）",
        )
        return y

    # 本地解密
    def decrypt(self, ciphers: Sequence[bytes]) -> bytes:
        assert self.k is not None
        return unmask(ciphers[self.sigma], self.k)


def ot_n_choose_1(messages: Sequence[bytes], sigma: int, bits: int = 1024,
                  key: Optional[RSAKey] = None, ch: Optional[Channel] = None,
                  sender_name: str = "Sender", receiver_name: str = "Receiver",
                  verbose: bool = False):
    """
    执行一次 1-out-of-n 不经意传输。

    返回 (解密得到的消息, 信道, 发送方对象, 接收方对象)
    """
    if ch is None:
        ch = Channel()

    sender = OTSender(sender_name, messages, key=key, bits=bits)
    receiver = OTReceiver(receiver_name, sigma)

    N, e, xs = sender.round1(ch, receiver.name)
    y = receiver.round2(ch, sender.name, N, e, xs)
    ciphers = sender.round3(ch, receiver.name, y)
    plain = receiver.decrypt(ciphers)

    if verbose:
        print(ch.summary())
    return plain, ch, sender, receiver


def ot_n_choose_1_text(options: Sequence[str], sigma: int, bits: int = 1024,
                       key: Optional[RSAKey] = None,
                       ch: Optional[Channel] = None,
                       verbose: bool = False) -> str:
    """字符串版本：内部自动做定长填充，返回解出的字符串。"""
    from common import pad_block

    blocks = [pad_block(s, MESSAGE_BLOCK) for s in options]
    raw, used_ch, _s, _r = ot_n_choose_1(
        blocks, sigma, bits=bits, key=key, ch=ch, verbose=verbose
    )
    return unpad_block(raw)
