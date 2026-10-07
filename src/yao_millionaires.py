# -*- coding: utf-8 -*-
"""
任务一：百万富翁问题的原始求解方案（Yao, 1982）
================================================

角色约定（一轮协议）
--------------------
* **加密方 P**（持有财富 ``w_p``）：生成 RSA 密钥、做私钥运算与"加 1"扰动；
* **判定方 Q**（持有财富 ``w_q``）：用公钥盲化自己的财富、最后做一次相等性检验。

一轮协议流程
------------
1. P 生成 RSA 密钥对 ``(n, e, d)``，把公钥 ``(n, e)`` 发给 Q。
2. Q 选随机数 ``x``（|x| ≈ |n|），计算 ``C = x^e mod n``，
   发送 ``k = (C - w_q) mod n``（把财富"藏"在随机数后面）。
3. P 对全部 N 个候选位置做私钥运算并模素数 p 压缩：

   ``Y_i = (k + i)^d mod n``  （i = 1..N） ， ``Z_i = Y_i mod p``

   其中 p 是 P 随机选取的素数，必须满足**间距检验**：

     * 任意 i≠j 有 |Z_i − Z_j| ≥ 2（保证"加 1"不会撞上别的 Z_j）；
     * 任意 i 有 Z_i ≤ p − 2（保证"加 1"不越过模数边界）。

   不满足则**换一个新素数 p 重试**。
   随后 P 依据自身财富做扰动：i ≤ w_p 时原样发送 Z_i，
   i > w_p 时发送 Z_i + 1。把 ``(p, W_1..W_N)`` 发给 Q。
4. Q 计算 ``G = x mod p``，只检查**自己那一个位置**：

   ``W_{w_q} == G``  ⟺  ``w_q ≤ w_p``（即 P 的财富 ≥ Q 的财富）

   因为当 i = w_q 时 ``Y_{w_q} = (k + w_q)^d = C^d = x``，
   于是 ``Z_{w_q} = x mod p = G``；P 是否"加 1"就泄露了大小关系。

单轮只能区分 ``a ≥ b`` 与 ``a < b``。**交换角色**、用**全新随机数**再跑一轮，
即可区分相等：

* 第一轮得 a ≥ b，第二轮得 b ≥ a  ⟹  a == b
* 第一轮得 a ≥ b，第二轮得 b < a  ⟹  a > b
* 第一轮得 a <  b，第二轮得 b ≥ a  ⟹  a < b
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from common import (
    COUNTERS,
    Channel,
    MSG_ALICE_RICHER,
    MSG_BOB_RICHER,
    MSG_EQUAL,
    RSAKey,
    Timer,
    gen_prime,
    gen_rsa_keypair,
    modexp,
    rand_below,
)


# ---------------------------------------------------------------------------
# 参与方：只持有自己的私有输入
# ---------------------------------------------------------------------------


class YaoEncryptor:
    """加密方 P：持有 RSA 密钥与财富 w_p，负责私钥运算与扰动。"""

    def __init__(self, name: str, wealth: int, key: RSAKey) -> None:
        self.name = name
        self.wealth = wealth          # 私有输入 w_p
        self.key = key                # 私有密钥 d（公钥部分会公开）
        # 协议执行期间才知道的信息
        self.learned: List[str] = []  # 半诚实视角下"可见信息"清单

    # 步骤 1：公开公钥
    def step1_public_key(self, ch: Channel, peer: str) -> Tuple[int, int]:
        ch.send(
            self.name, peer, (self.key.n, self.key.e),
            "步骤1  RSA 公钥 (n, e)",
        )
        return self.key.n, self.key.e

    # 步骤 3：私钥运算 + 模素数压缩 + 依据自身财富扰动
    def step3_transform(self, ch: Channel, peer: str, k: int, N: int,
                        p_bits: int) -> Tuple[int, List[int]]:
        n, d = self.key.n, self.key.d

        # --- 模运算边界处理：k + i 可能越过 n，统一先取模 ---
        nums = [(k + i) % n for i in range(1, N + 1)]

        # --- 选素数 p 并做间距检验，不满足则失败重试 ---
        while True:
            COUNTERS.prime_retry += 1
            p = gen_prime(p_bits)
            # Y_i = (k+i)^d mod n —— N 次私钥模幂，是本方案的主要计算开销
            Y = [modexp(v, d, n) for v in nums]
            Z = [y % p for y in Y]

            ok = True
            if Z:                       # (b) 模数边界：Z_i + 1 不得越过 p
                if max(Z) + 1 >= p:
                    ok = False
            if ok:                      # (a) 余数间距检验：任意两个 Z 至少相差 2
                srt = sorted(Z)
                for idx in range(1, len(srt)):
                    if srt[idx] - srt[idx - 1] < 2:
                        ok = False
                        break
            if ok:
                break

        # --- 依据自身财富做扰动：i ≤ a 原样，i > a 加 1 ---
        W = [Z[i] if (i + 1) <= self.wealth else Z[i] + 1 for i in range(N)]
        ch.send(
            self.name, peer, [p] + W,
            f"步骤3  素数 p 与 N={N} 个压缩值 W_i（已按自身财富扰动）",
        )
        return p, W


class YaoDecider:
    """判定方 Q：持有财富 w_q，负责盲化与最终判定。"""

    def __init__(self, name: str, wealth: int) -> None:
        self.name = name
        self.wealth = wealth          # 私有输入 w_q
        self.learned: List[str] = []
        self._x: Optional[int] = None  # 本轮随机数（用完即弃）

    # 步骤 2：盲化自己的财富
    def step2_blind(self, ch: Channel, peer: str, n: int, e: int) -> int:
        x = rand_below(n)
        self._x = x
        C = modexp(x, e, n)                 # RSA 公钥变换
        k = (C - self.wealth) % n           # 边界处理：C - b 可能为负
        ch.send(
            self.name, peer, k,
            "步骤2  k = x^e mod n − b（财富被随机数盲化）",
        )
        return k

    # 步骤 4：只检查自己的位置
    def step4_decide(self, ch: Channel, peer: str, p: int,
                     W: List[int]) -> bool:
        assert self._x is not None
        G = self._x % p
        # 只比较自己那一位，其余 W_i 无法利用（不知道私钥 d）
        result = (W[self.wealth - 1] == G)
        ch.send(
            self.name, peer, 1 if result else 0,
            "步骤4  判定结果 1 比特（True = 加密方财富 ≥ 判定方财富）",
        )
        return result


# ---------------------------------------------------------------------------
# 单轮 / 完整协议
# ---------------------------------------------------------------------------


def yao_compare_once(ch: Channel, encryptor: YaoEncryptor, decider: YaoDecider,
                     N: int, p_bits: int) -> bool:
    """
    执行**一轮** Yao 协议。

    返回 True  ⟺  加密方财富 ≥ 判定方财富（w_p ≥ w_q）。
    注意：单轮无法区分"大于"与"等于"。
    """
    # 1) 加密方公开 RSA 公钥
    n, e = encryptor.step1_public_key(ch, decider.name)
    # 2) 判定方盲化财富并回送 k
    k = decider.step2_blind(ch, encryptor.name, n, e)
    # 3) 加密方做私钥运算、模 p 压缩并按自身财富扰动
    p, W = encryptor.step3_transform(ch, decider.name, k, N, p_bits)
    # 4) 判定方只检查自己的位置
    return decider.step4_decide(ch, encryptor.name, p, W)


def yao_millionaires(a: int, b: int, N: int, bits: int,
                     p_bits: Optional[int] = None,
                     key_a: Optional[RSAKey] = None,
                     key_b: Optional[RSAKey] = None,
                     verbose: bool = False) -> Tuple[str, Channel, dict]:
    """
    用 Yao 原始方案完整求解百万富翁问题（含相等判定）。

    参数
    ----
    a, b    : Alice / Bob 的财富，取值 1..N
    N       : 财富上界（公开参数）
    bits    : RSA 模数比特长度
    key_a/b : 可选，复用已生成的 RSA 密钥（密钥与随机数独立，复用不影响安全性）

    返回
    ----
    (结果字符串, 信道对象, 统计字典)
    """
    if p_bits is None:
        p_bits = max(64, bits // 4)   # 默认取 |n|/4，使间距检验以压倒性概率一次通过

    if key_a is None:
        key_a = gen_rsa_keypair(bits)
    if key_b is None:
        key_b = gen_rsa_keypair(bits)

    ch = Channel()
    COUNTERS.reset()

    # ---- 第一轮：Alice 做加密方，判定 a ≥ b ----
    alice_enc = YaoEncryptor("Alice", a, key_a)
    bob_dec = YaoDecider("Bob", b)
    r1 = yao_compare_once(ch, alice_enc, bob_dec, N, p_bits)

    # ---- 第二轮：角色互换、全新随机数与全新密钥，判定 b ≥ a ----
    bob_enc = YaoEncryptor("Bob", b, key_b)
    alice_dec = YaoDecider("Alice", a)
    r2 = yao_compare_once(ch, bob_enc, alice_dec, N, p_bits)

    if r1 and r2:
        result = MSG_EQUAL
    elif r1:
        result = MSG_ALICE_RICHER
    elif r2:
        result = MSG_BOB_RICHER
    else:
        result = "协议异常（两轮结果矛盾）"

    stats = {
        "rounds": ch.rounds,
        "bytes": ch.bytes,
        "modexp": COUNTERS.modexp,
        "p_retry": COUNTERS.prime_retry,
        "r1_alice_ge_bob": r1,
        "r2_bob_ge_alice": r2,
    }
    if verbose:
        print(ch.summary())
    return result, ch, stats
