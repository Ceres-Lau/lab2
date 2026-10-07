# -*- coding: utf-8 -*-
"""
任务二（下半）：用 n 选 1 不经意传输解决百万富翁问题
====================================================

思路（一次 OT 直接得到三态结果）
--------------------------------
设财富取值范围为 1..N（N 为公开上界）。

Alice 作为 **OT 发送方**，构造 N 条消息，第 i 条（i = 1..N）的内容是
"把 Alice 的财富 a 与 i 做比较"的结果：

        m_i = "Alice 更富有"   若 i < a
        m_i = "双方财富相等"   若 i == a
        m_i = "Bob   更富有"   若 i > a

Bob 作为 **OT 接收方**，以 σ = b − 1 执行一次 1-out-of-N OT，取出 m_b，
即 cmp(a, b)，正好就是题目要求的输出。

为什么这是安全的（半诚实模型）
------------------------------
* **Alice（发送方）**：OT 的接收方隐私保证她看不到 σ，因此不知道 b；
  她最终只知道双方共同的输出（若协议约定 Bob 回传结果比特）。
* **Bob（接收方）**：OT 的发送方隐私保证他只能解开 m_b，
  其余 m_i（i ≠ b）仍是 H(k_i) 掩码下的乱码，因此学不到 a 的任何额外信息。
  他能学到的，恰好只是"比较结果"这一个三态值——这正是问题的允许输出。

与"逐位比较 + 多次 OT"的替代方案相比，本方案只需 **1 次 1-out-of-N OT、
3 轮交互**，且天然区分相等，无需交换角色再跑一轮。

输出约定：为与任务一保持一致，比较结果由 Bob 用一个定长块回传给 Alice，
使双方都得到相同的结论（回传内容本身就是允许公开的输出）。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from common import (
    COUNTERS,
    Channel,
    MESSAGE_BLOCK,
    MSG_ALICE_RICHER,
    MSG_BOB_RICHER,
    MSG_EQUAL,
    RSAKey,
    pad_block,
    unpad_block,
)

from ot_rsa import OTSender, OTReceiver


def compare_label(a: int, i: int) -> str:
    """把 a 与候选值 i 的比较结果写成三态字符串。"""
    if i < a:
        return MSG_ALICE_RICHER
    if i == a:
        return MSG_EQUAL
    return MSG_BOB_RICHER


def build_ot_messages(a: int, N: int) -> List[bytes]:
    """Alice 构造 N 条消息：m_i = cmp(a, i)，i = 1..N，并做定长填充。"""
    return [pad_block(compare_label(a, i), MESSAGE_BLOCK) for i in range(1, N + 1)]


def ot_millionaires(a: int, b: int, N: int, bits: int = 1024,
                    key: Optional[RSAKey] = None, verbose: bool = False,
                    with_ack: bool = True) -> Tuple[str, Channel, dict]:
    """
    用 1-out-of-N OT 求解百万富翁问题。

    返回 (结果字符串, 信道对象, 统计字典)。
    """
    ch = Channel()
    COUNTERS.reset()

    # --- Alice：发送方，持有财富 a ---
    messages = build_ot_messages(a, N)
    alice = OTSender("Alice", messages, key=key, bits=bits)

    # --- Bob：接收方，持有财富 b，选择 σ = b − 1 ---
    bob = OTReceiver("Bob", b - 1)

    # 第 1 轮：Alice → Bob，公钥与 N 个盲化因子
    N_mod, e, xs = alice.round1(ch, bob.name)
    # 第 2 轮：Bob → Alice，盲化后的选择
    y = bob.round2(ch, alice.name, N_mod, e, xs)
    # 第 3 轮：Alice → Bob，N 条加密消息
    ciphers = alice.round3(ch, bob.name, y)
    # Bob 本地解密
    plain = bob.decrypt(ciphers)
    result = unpad_block(plain)

    if with_ack:
        # Bob 把"比较结果"这一个三态值定长回传给 Alice，使双方得到一致结论。
        # 回传的内容就是问题的允许输出，不构成额外泄露。
        ch.send(
            "Bob", "Alice", pad_block(result, MESSAGE_BLOCK),
            "结果回传  双方共同输出（三态结果本身）",
        )

    stats = {
        "rounds": ch.rounds,
        "bytes": ch.bytes,
        "modexp": COUNTERS.modexp,
        "sigma": bob.sigma,      # 仅用于测试校验：协议内 Alice 看不到
    }
    if verbose:
        print(ch.summary())
    return result, ch, stats
