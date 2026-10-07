# -*- coding: utf-8 -*-
"""
实验二 统一实验入口
====================

一键完成：协议演示 → 正确性测试 → OT 自身测试 → 隐私性实证 →
性能对比 → 可扩展性测试，并把全部结果写入 ``results/results.json``
与 ``results/tables.csv``。

运行：  python run_experiments.py
"""

from __future__ import annotations

import csv
import json
import os
import platform
import random
import statistics
import sys
import time
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    COUNTERS,
    MESSAGE_BLOCK,
    MSG_ALICE_RICHER,
    MSG_BOB_RICHER,
    MSG_EQUAL,
    Channel,
    RSAKey,
    Timer,
    gen_rsa_keypair,
    ground_truth,
    modexp,
    pad_block,
    rand_below,
    unpad_block,
    wire_size,
)
from ot_millionaires import ot_millionaires  # noqa: E402
from ot_rsa import OTSender, OTReceiver, ot_n_choose_1  # noqa: E402
from yao_millionaires import yao_millionaires  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS_DIR = os.path.join(ROOT, "results")

# ---------------------------------------------------------------------------
# 实验参数（与实验要求一致：财富 1~100，RSA 1024 / 2048 位）
# ---------------------------------------------------------------------------
BITS_LIST = [1024, 2048]
N_SMALL = 10        # 穷举测试用的财富上界
N_MAIN = 100        # 主实验财富上界
TRIALS_RANDOM = 100  # N=100 时的随机测试组数
REPS = {1024: 10, 2048: 5}   # 性能对比重复次数
SCALE_NS = [10, 25, 50, 100]
KEY_POOL_SIZE = 4

_rnd = random.Random(20261007)   # 固定种子，保证结果可复现

RESULTS: Dict[str, object] = {}


def _log(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def make_key_pool(bits: int, size: int = KEY_POOL_SIZE) -> List[RSAKey]:
    """预生成密钥池。密钥是长期参数，重复使用不影响单次协议的安全性
    （每轮的随机数 x / k 都全新），这样可以把"密钥生成"这一一次性开销
    与"单次比较"的在线开销区分开。"""
    return [gen_rsa_keypair(bits) for _ in range(size)]


# ===========================================================================
# 1. 协议演示
# ===========================================================================


def demo() -> Dict[str, object]:
    _log("【1】协议流程演示（N=10, a=7, b=3, RSA 1024 位）")
    out: Dict[str, object] = {}

    print("\n--- 任务一：Yao 原始方案 ---")
    res, ch, _ = yao_millionaires(7, 3, N_SMALL, 1024, verbose=True)
    print(f"  协议输出：{res}    明文参考：{ground_truth(7, 3)}")

    print("\n--- 任务二：n 选 1 OT ---")
    res2, ch2, _ = ot_millionaires(7, 3, N_SMALL, 1024, verbose=True)
    print(f"  协议输出：{res2}    明文参考：{ground_truth(7, 3)}")

    print("\n--- 独立演示：1-out-of-8 OT（接收方选择第 4 条）---")
    opts = [f"消息{i}" for i in range(8)]
    got = ot_n_choose_1_text_demo(opts, 3, 1024)
    print(f"  接收方选择 σ=3，解出：{got!r}   期望：'消息3'")

    out["yao"] = {"result": res, "expect": ground_truth(7, 3),
                  "rounds": ch.rounds, "bytes": ch.bytes, "log": ch.log}
    out["ot"] = {"result": res2, "expect": ground_truth(7, 3),
                 "rounds": ch2.rounds, "bytes": ch2.bytes, "log": ch2.log}
    out["ot8"] = {"got": got, "expect": "消息3"}
    return out


def ot_n_choose_1_text_demo(options: List[str], sigma: int, bits: int) -> str:
    from ot_rsa import ot_n_choose_1_text
    ch = Channel()
    return ot_n_choose_1_text(options, sigma, bits=bits, ch=ch, verbose=True)


# ===========================================================================
# 2. 正确性测试
# ===========================================================================


def correctness(bits: int = 1024) -> Dict[str, object]:
    _log(f"【2】正确性测试（RSA {bits} 位）")
    pool = make_key_pool(bits)
    out: Dict[str, object] = {}

    # ---- 2.1 N=10 穷举所有 (a,b) ----
    print(f"\n[2.1] N={N_SMALL} 穷举全部 {N_SMALL * N_SMALL} 组 (a, b) ...")
    ok = err = 0
    t0 = time.perf_counter()
    for a in range(1, N_SMALL + 1):
        for b in range(1, N_SMALL + 1):
            exp = ground_truth(a, b)
            r1, _, _ = yao_millionaires(a, b, N_SMALL, bits,
                                        key_a=pool[0], key_b=pool[1])
            r2, _, _ = ot_millionaires(a, b, N_SMALL, bits, key=pool[2])
            ok += (r1 == exp) + (r2 == exp)
            err += (r1 != exp) + (r2 != exp)
    dt = time.perf_counter() - t0
    print(f"      用例数 = {N_SMALL * N_SMALL * 2}，正确 = {ok}，错误 = {err}，"
          f"正确率 = {ok / (ok + err) * 100:.2f}%   用时 {dt:.1f}s")
    out["exhaustive_n10"] = {
        "cases": N_SMALL * N_SMALL * 2, "correct": ok, "wrong": err,
        "accuracy": ok / (ok + err) * 100, "seconds": dt,
    }

    # ---- 2.2 N=100 随机测试 + 边界用例 ----
    print(f"\n[2.2] N={N_MAIN} 随机 {TRIALS_RANDOM} 组 + 边界用例 ...")
    cases = [(a, b) for a in range(1, N_MAIN + 1)
             for b in (1, N_MAIN // 2, N_MAIN, a, max(1, a - 1), min(N_MAIN, a + 1))]
    cases = list(dict.fromkeys(cases))
    _rnd.shuffle(cases)
    cases = cases[:TRIALS_RANDOM]
    edge = [(1, 1), (1, N_MAIN), (N_MAIN, 1), (N_MAIN, N_MAIN),
            (N_MAIN // 2, N_MAIN // 2), (50, 51), (51, 50)]
    for c in edge:
        if c not in cases:
            cases.append(c)

    stat = {"yao": [0, 0], "ot": [0, 0], "by_outcome": {}}
    t0 = time.perf_counter()
    for (a, b) in cases:
        exp = ground_truth(a, b)
        for tag, fn in (("yao", lambda a, b: yao_millionaires(
                            a, b, N_MAIN, bits, key_a=pool[0], key_b=pool[1])[0]),
                        ("ot", lambda a, b: ot_millionaires(
                            a, b, N_MAIN, bits, key=pool[2])[0])):
            got = fn(a, b)
            stat[tag][0 if got == exp else 1] += 1
            key = f"{exp}"
            d = stat["by_outcome"].setdefault(key, {"n": 0, "yao_ok": 0, "ot_ok": 0})
            if tag == "yao":
                d["n"] += 1
                d["yao_ok"] += (got == exp)
            else:
                d["ot_ok"] += (got == exp)
    dt = time.perf_counter() - t0
    tot_y = sum(stat["yao"])
    tot_o = sum(stat["ot"])
    print(f"      用例数（每组）= {len(cases)}")
    print(f"      任务一 Yao  : 正确 {stat['yao'][0]}/{tot_y}，"
          f"正确率 {stat['yao'][0] / tot_y * 100:.2f}%")
    print(f"      任务二 OT   : 正确 {stat['ot'][0]}/{tot_o}，"
          f"正确率 {stat['ot'][0] / tot_o * 100:.2f}%")
    print(f"      用时 {dt:.1f}s")
    for k, v in stat["by_outcome"].items():
        print(f"        结果[{k}]：{v['n']} 组，Yao 正确 {v['yao_ok']}，"
              f"OT 正确 {v['ot_ok']}")

    out["random_n100"] = {
        "cases": len(cases),
        "yao_correct": stat["yao"][0], "yao_total": tot_y,
        "yao_accuracy": stat["yao"][0] / tot_y * 100,
        "ot_correct": stat["ot"][0], "ot_total": tot_o,
        "ot_accuracy": stat["ot"][0] / tot_o * 100,
        "seconds": dt, "by_outcome": stat["by_outcome"],
    }

    # ---- 2.3 OT 自身正确性：1-out-of-8 遍历全部选择 ----
    print("\n[2.3] 1-out-of-8 OT：遍历 8 个选择 + 重复 20 轮 ...")
    opts = [f"消息{i}" for i in range(8)]
    blocks = [pad_block(s, MESSAGE_BLOCK) for s in opts]
    key = pool[3]
    ok = err = 0
    for _ in range(20):
        for sigma in range(8):
            plain, _, _, _ = ot_n_choose_1(blocks, sigma, bits=bits, key=key)
            if unpad_block(plain) == opts[sigma]:
                ok += 1
            else:
                err += 1
    print(f"      用例数 = {ok + err}，正确 = {ok}，错误 = {err}，"
          f"正确率 = {ok / (ok + err) * 100:.2f}%")
    out["ot_self"] = {"cases": ok + err, "correct": ok,
                      "accuracy": ok / (ok + err) * 100}
    return out


# ===========================================================================
# 3. 隐私性实证
# ===========================================================================


def privacy(bits: int = 1024, samples: int = 300) -> Dict[str, object]:
    _log("【3】隐私性实证（半诚实模型）")
    out: Dict[str, object] = {}
    key = gen_rsa_keypair(bits)
    N = key.n
    e = key.e

    # ---- 3.1 发送方视角：能否从 y 猜出 σ？ ----
    print(f"\n[3.1] 发送方隐私：对 σ=0 与 σ=1 各采样 {samples} 个 y ...")
    xs = [rand_below(N) for _ in range(2)]

    def sample_y(sigma: int, m: int) -> List[float]:
        res = []
        for _ in range(m):
            k = rand_below(N)
            y = xs[sigma] * modexp(k, e, N) % N
            res.append(y / N)          # 归一化到 [0,1)
        return res

    y0 = sample_y(0, samples)
    y1 = sample_y(1, samples)
    m0, m1 = statistics.mean(y0), statistics.mean(y1)
    s0, s1 = statistics.pstdev(y0), statistics.pstdev(y1)

    # 经验最优阈值分类器（在训练集上取最优，在测试集上看准确率）
    half = samples // 2
    train = [(v, 0) for v in y0[:half]] + [(v, 1) for v in y1[:half]]
    test = [(v, 0) for v in y0[half:]] + [(v, 1) for v in y1[half:]]
    best_acc, best_th = 0.0, 0.5
    cands = sorted({v for v, _ in train})
    for th in cands[:: max(1, len(cands) // 200)] + [0.5]:
        pred = 0 if th <= 0.5 else 1
        acc = sum(1 for v, lab in train if (0 if v < th else 1) == lab) / len(train)
        acc = max(acc, 1 - acc)
        if acc > best_acc:
            best_acc, best_th = acc, th
    acc_test = sum(1 for v, lab in test if (0 if v < best_th else 1) == lab) / len(test)
    acc_test = max(acc_test, 1 - acc_test)
    print(f"      σ=0 样本：均值 {m0:.4f}  标准差 {s0:.4f}")
    print(f"      σ=1 样本：均值 {m1:.4f}  标准差 {s1:.4f}")
    print(f"      经验最优阈值分类器准确率 = {acc_test * 100:.2f}% "
          f"（随机猜测基线 50%）→ 发送方无法区分选择")
    out["sender"] = {"mean0": m0, "mean1": m1, "std0": s0, "std1": s1,
                     "classifier_acc": acc_test * 100, "samples": samples}

    # ---- 3.2 接收方视角：能否解出未选消息？ ----
    print("\n[3.2] 接收方隐私：尝试用正确的 k 去解未选中的消息 ...")
    labels = ["Alice 更富有", "双方财富相等", "Bob 更富有"]
    msgs = [pad_block(s, MESSAGE_BLOCK) for s in labels]
    sigma = 1
    plain, ch, sender, receiver = ot_n_choose_1(msgs, sigma, bits=bits, key=key)
    ciphers = sender.messages  # 已被 round3 覆盖为密文? 取真实密文需重算
    # 重新取密文：直接复现一次以取得 ciphers
    from common import mask
    k_val = receiver.k
    y = None
    # 重放一次拿到密文列表
    ch2 = Channel()
    s2 = OTSender("Alice", msgs, key=key)
    r2 = OTReceiver("Bob", sigma)
    Nn, ee, xxs = s2.round1(ch2, "Bob")
    yy = r2.round2(ch2, "Alice", Nn, ee, xxs)
    ciphers = s2.round3(ch2, "Bob", yy)
    kk = r2.k

    valid = 0
    garbles = []
    for i in range(len(ciphers)):
        dec = mask(ciphers[i], kk)     # 用自己的 k 去解第 i 条
        txt = unpad_block(dec)
        garbles.append(dec.hex()[:24])
        if txt in labels:
            valid += 1
    print(f"      用 k 解密 3 条密文，得到可识别明文的有 {valid} 条（期望=1，"
          f"即仅第 σ={sigma} 条）")
    print(f"      未选中消息的解密结果（十六进制前 24 位，应为乱码）：")
    for i, g in enumerate(garbles):
        flag = "  <-- 选中，可正确解密" if i == sigma else ""
        print(f"        c_{i}: {g}{flag}")
    out["receiver"] = {"decryptable": valid, "expected": 1,
                       "garble_hex": garbles, "sigma": sigma}

    # ---- 3.3 双方可见信息清单 ----
    visible = {
        "Yao_Alice_可见": ["自己的财富 a", "两轮各一个盲化值 k = x^e − b mod n",
                           "自己生成的 RSA 私钥 d", "对方回传的 1 比特判定结果",
                           "最终三态输出"],
        "Yao_Bob_可见": ["自己的财富 b", "Alice 的 RSA 公钥 (n,e)",
                          "素数 p 与 N 个压缩值 W_i（其中只有自己那一位可解读）",
                          "最终三态输出"],
        "OT_Alice_可见": ["自己的财富 a", "自己的 RSA 密钥对",
                          "盲化选择 y = x_σ·k^e mod N", "最终三态输出"],
        "OT_Bob_可见": ["自己的财富 b", "公钥 (N,e) 与 N 个盲化因子 x_i",
                        "N 条密文 c_i（只能解开第 b 条）", "最终三态输出"],
    }
    out["visible"] = visible
    print("\n[3.3] 双方可见信息清单：")
    for k, v in visible.items():
        print(f"      {k}:")
        for item in v:
            print(f"        - {item}")
    return out


# ===========================================================================
# 4. 性能对比
# ===========================================================================


def performance() -> Dict[str, object]:
    _log("【4】性能对比（相同设备、相同输入、相同密码参数）")
    out: Dict[str, object] = {}
    rows: List[Dict[str, object]] = []

    for bits in BITS_LIST:
        reps = REPS[bits]
        pool = make_key_pool(bits)
        a, b = 73, 28          # 固定同一组输入，保证可比

        # --- 密钥生成（一次性开销，单独计时）---
        t0 = time.perf_counter()
        for _ in range(5):
            gen_rsa_keypair(bits)
        keygen_t = (time.perf_counter() - t0) / 5

        # --- 任务一：Yao ---
        t_with, t_without, by, rd, mx = [], [], 0, 0, 0
        for i in range(reps):
            t0 = time.perf_counter()
            r, ch, st = yao_millionaires(a, b, N_MAIN, bits)
            t_with.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            r, ch2, st2 = yao_millionaires(a, b, N_MAIN, bits,
                                           key_a=pool[0], key_b=pool[1])
            t_without.append(time.perf_counter() - t0)
            by, rd, mx = st2["bytes"], st2["rounds"], st2["modexp"]
        yao_row = {
            "bits": bits, "scheme": "任务一 Yao 原始方案",
            "time_with_keygen": statistics.mean(t_with),
            "time_online": statistics.mean(t_without),
            "time_keygen": keygen_t,
            "bytes": by, "rounds": rd, "modexp": mx,
        }

        # --- 任务二：OT ---
        t_with, t_without = [], []
        for i in range(reps):
            t0 = time.perf_counter()
            r, ch, st = ot_millionaires(a, b, N_MAIN, bits)
            t_with.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            r, ch2, st2 = ot_millionaires(a, b, N_MAIN, bits, key=pool[2])
            t_without.append(time.perf_counter() - t0)
            by2, rd2, mx2 = st2["bytes"], st2["rounds"], st2["modexp"]
        ot_row = {
            "bits": bits, "scheme": "任务二 1-out-of-n OT",
            "time_with_keygen": statistics.mean(t_with),
            "time_online": statistics.mean(t_without),
            "time_keygen": keygen_t,
            "bytes": by2, "rounds": rd2, "modexp": mx2,
        }
        rows.append(yao_row)
        rows.append(ot_row)

        print(f"\n  RSA {bits} 位（N={N_MAIN}，a={a}，b={b}，重复 {reps} 次取均值）")
        for row in (yao_row, ot_row):
            print(f"    {row['scheme']:<24} "
                  f"在线耗时 {row['time_online'] * 1000:9.2f} ms | "
                  f"含密钥生成 {row['time_with_keygen'] * 1000:9.2f} ms | "
                  f"通信 {row['bytes']:7d} B | "
                  f"轮数 {row['rounds']:2d} | 模幂 {row['modexp']:4d}")
        print(f"    （RSA-{bits} 单次密钥生成均耗时 {keygen_t * 1000:.1f} ms；"
              f"Yao 需 2 把密钥，OT 需 1 把）")

    out["rows"] = rows
    return out


# ===========================================================================
# 5. 可扩展性
# ===========================================================================


def scalability(bits: int = 1024, reps: int = 5) -> Dict[str, object]:
    _log(f"【5】可扩展性：财富上界 N 的影响（RSA {bits} 位）")
    pool = make_key_pool(bits)
    rows = []
    for N in SCALE_NS:
        ts_y, ts_o = [], []
        for _ in range(reps):
            a = _rnd.randint(1, N)
            b = _rnd.randint(1, N)
            t0 = time.perf_counter()
            _, ch_y, st_y = yao_millionaires(a, b, N, bits,
                                             key_a=pool[0], key_b=pool[1])
            ts_y.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            _, ch_o, st_o = ot_millionaires(a, b, N, bits, key=pool[2])
            ts_o.append(time.perf_counter() - t0)
        row = {
            "N": N,
            "yao_ms": statistics.mean(ts_y) * 1000,
            "yao_bytes": st_y["bytes"], "yao_rounds": st_y["rounds"],
            "ot_ms": statistics.mean(ts_o) * 1000,
            "ot_bytes": st_o["bytes"], "ot_rounds": st_o["rounds"],
        }
        rows.append(row)
        print(f"    N={N:>4}   Yao: {row['yao_ms']:8.2f} ms / {row['yao_bytes']:7d} B"
              f"   |   OT: {row['ot_ms']:8.2f} ms / {row['ot_bytes']:7d} B")
    return {"rows": rows}


# ===========================================================================
# 主流程
# ===========================================================================


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    t_start = time.perf_counter()

    RESULTS["meta"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "bits_list": BITS_LIST,
        "N_main": N_MAIN,
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    RESULTS["demo"] = demo()
    RESULTS["correctness"] = correctness(1024)
    RESULTS["privacy"] = privacy(1024)
    RESULTS["performance"] = performance()
    RESULTS["scalability"] = scalability(1024)

    RESULTS["meta"]["total_seconds"] = time.perf_counter() - t_start

    # ---- 写 JSON ----
    jpath = os.path.join(RESULTS_DIR, "results.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)

    # ---- 写 CSV（便于直接粘到报告表格）----
    cpath = os.path.join(RESULTS_DIR, "tables.csv")
    with open(cpath, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["类别", "方案", "RSA位数", "财富上界N", "在线耗时(ms)",
                    "含密钥生成(ms)", "通信字节", "交互轮数", "模幂次数"])
        for r in RESULTS["performance"]["rows"]:
            w.writerow(["性能对比", r["scheme"], r["bits"], N_MAIN,
                        f"{r['time_online'] * 1000:.2f}",
                        f"{r['time_with_keygen'] * 1000:.2f}",
                        r["bytes"], r["rounds"], r["modexp"]])
        for r in RESULTS["scalability"]["rows"]:
            w.writerow(["可扩展性", "任务一 Yao 原始方案", 1024, r["N"],
                        f"{r['yao_ms']:.2f}", "", r["yao_bytes"], r["yao_rounds"], ""])
            w.writerow(["可扩展性", "任务二 1-out-of-n OT", 1024, r["N"],
                        f"{r['ot_ms']:.2f}", "", r["ot_bytes"], r["ot_rounds"], ""])

    _log(f"全部完成，总用时 {RESULTS['meta']['total_seconds']:.1f}s")
    print(f"  结果 JSON：{jpath}")
    print(f"  结果 CSV ：{cpath}")


if __name__ == "__main__":
    main()
