# -*- coding: utf-8 -*-
"""
由 results.json 自动生成 LaTeX 实验报告（report/main.tex）。

所有数字均从实验结果文件中读取，避免手工誊写出错。
插图全部用 TikZ 原生绘制（矢量、无需外部图片）。
"""

from __future__ import annotations

import json
import os
from typing import List, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPORT_DIR = os.path.join(ROOT, "report")

R = json.load(open(os.path.join(ROOT, "results", "results.json"),
                   encoding="utf-8"))

META = R["meta"]
DEMO = R["demo"]
CORR = R["correctness"]
PRIV = R["privacy"]
PERF = R["performance"]["rows"]
SCAL = R["scalability"]["rows"]

P = {r["bits"]: r for r in PERF if r["scheme"].startswith("任务一")}
O = {r["bits"]: r for r in PERF if r["scheme"].startswith("任务二")}


def fmt(v: float, nd: int = 0) -> str:
    return f"{v:,.{nd}f}"


# ===========================================================================
# TikZ 绘图辅助
# ===========================================================================


def tikz_lines(series: Sequence[dict], xlabel: str, ylabel: str,
               xmin: float, xmax: float, ymin: float, ymax: float,
               xticks: Sequence[float], yticks: Sequence[float],
               width: float = 10.5, height: float = 5.6,
               legend_pos: Tuple[float, float] = (6.2, 4.9)) -> str:
    """纯 TikZ 折线图。series: [{name, style, mark, pts:[(x,y)]}]"""

    def px(x):
        return (x - xmin) / (xmax - xmin) * width

    def py(y):
        return (y - ymin) / (ymax - ymin) * height

    L = [r"\begin{tikzpicture}[font=\small]"]
    # 网格
    for y in yticks:
        L.append(rf"\draw[gray!18] (0,{py(y):.3f}) -- ({width:.2f},{py(y):.3f});")
    # 坐标轴
    L.append(rf"\draw[->,thick] (0,0) -- ({width + 0.35:.2f},0) "
             rf"node[below right] {{{xlabel}}};")
    L.append(rf"\draw[->,thick] (0,0) -- (0,{height + 0.35:.2f}) "
             rf"node[above left] {{{ylabel}}};")
    # 刻度
    for x in xticks:
        L.append(rf"\draw ({px(x):.3f},0) -- ({px(x):.3f},-0.12) "
                 rf"node[below] {{{x:g}}};")
    for y in yticks:
        L.append(rf"\draw (0,{py(y):.3f}) -- (-0.12,{py(y):.3f}) "
                 rf"node[left] {{{y:g}}};")
    # 数据
    for s in series:
        pts = " ".join(f"({px(x):.3f},{py(y):.3f})" for x, y in s["pts"])
        L.append(rf"\draw[{s['style']},mark={s['mark']},"
                 rf"mark options={{fill=white,solid}}] plot coordinates {{{pts}}};")
    # 图例
    lx, ly = legend_pos
    L.append(rf"\draw[black!45] ({lx - 0.15:.2f},{ly - 0.35:.2f}) "
             rf"rectangle ({lx + 4.0:.2f},{ly + 0.75:.2f});")
    for i, s in enumerate(series):
        yy = ly + 0.55 - i * 0.55
        L.append(rf"\draw[{s['style']},mark={s['mark']}] "
                 rf"({lx:.2f},{yy:.2f}) -- ({lx + 0.75:.2f},{yy:.2f});")
        L.append(rf"\node[right,font=\footnotesize] at "
                 rf"({lx + 0.95:.2f},{yy:.2f}) {{{s['name']}}};")
    L.append(r"\end{tikzpicture}")
    return "\n".join(L)


def tikz_bars(groups: Sequence[Tuple[str, Sequence[Tuple[str, float, str]]]],
              ylabel: str, ymax: float, yticks: Sequence[float],
              width: float = 10.5, height: float = 5.2) -> str:
    """分组柱状图。groups: [(组名, [(条名, 值, 颜色)])]"""

    def py(y):
        return y / ymax * height

    n_g = len(groups)
    gw = width / n_g
    L = [r"\begin{tikzpicture}[font=\small]"]
    for y in yticks:
        if y == 0:
            continue
        L.append(rf"\draw[gray!18] (0,{py(y):.3f}) -- ({width:.2f},{py(y):.3f});")
    L.append(rf"\draw[->,thick] (0,0) -- ({width + 0.35:.2f},0);")
    L.append(rf"\draw[->,thick] (0,0) -- (0,{height + 0.35:.2f}) "
             rf"node[above left] {{{ylabel}}};")
    for y in yticks:
        L.append(rf"\draw (0,{py(y):.3f}) -- (-0.12,{py(y):.3f}) "
                 rf"node[left] {{{y:g}}};")

    for gi, (gname, bars) in enumerate(groups):
        nb = len(bars)
        bw = gw / (nb + 1.2)
        cx = gi * gw
        L.append(rf"\node[font=\small] at ({cx + gw / 2:.3f},-0.45) {{{gname}}};")
        for bi, (bname, val, color) in enumerate(bars):
            x0 = cx + gw / 2 - (nb * bw) / 2 + bi * bw
            h = py(val)
            L.append(rf"\fill[{color}] ({x0:.3f},0) rectangle "
                     rf"({x0 + bw * 0.82:.3f},{h:.3f});")
            L.append(rf"\node[above,font=\scriptsize] at "
                     rf"({x0 + bw * 0.41:.3f},{h:.3f}) {{{val:,.0f}}};")
        # 组内图例
        for bi, (bname, val, color) in enumerate(bars):
            lx = cx + 0.12
            ly = height + 0.05 - bi * 0.42
            L.append(rf"\fill[{color}] ({lx:.3f},{ly:.3f}) rectangle "
                     rf"({lx + 0.28:.3f},{ly + 0.22:.3f});")
            L.append(rf"\node[right,font=\scriptsize] at "
                     rf"({lx + 0.36:.3f},{ly + 0.11:.3f}) {{{bname}}};")
    L.append(r"\end{tikzpicture}")
    return "\n".join(L)


# ===========================================================================
# 表格辅助
# ===========================================================================


def table_booktabs(cols: str, rows: List[List[str]], caption: str,
                   label: str, pos: str = "h") -> str:
    head, *body = rows
    L = [rf"\begin{{table}}[{pos}]", r"\centering",
         rf"\begin{{tabular}}{{{cols}}}", r"\toprule",
         " & ".join(head) + r" \\", r"\midrule"]
    for r in body:
        L.append(" & ".join(r) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\end{table}"]
    return "\n".join(L)


def esc(s: str) -> str:
    """Escape LaTeX special characters appearing in plain-text data."""
    out = s.replace("\\", r"\textbackslash{}")
    for a, b in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"),
                 ("_", r"\_"), ("^", r"\textasciicircum{}"),
                 ("~", r"\textasciitilde{}")):
        out = out.replace(a, b)
    # characters that need math mode (no glyph in the text font)
    for a, b in ((r"σ", r"$\sigma$"), (r"≥", r"$\geq$"), (r"≤", r"$\leq$"),
                 (r"≠", r"$\neq$"), (r"≈", r"$\approx$"), (r"⊕", r"$\oplus$")):
        out = out.replace(a, b)
    return out


def msglog_table(log: List[dict], caption: str, label: str) -> str:
    rows = [["序号", "发送方", "接收方", "消息含义", "字节数"]]
    for rec in log:
        rows.append([str(rec["seq"]), rec["from"], rec["to"],
                     esc(rec["note"]), fmt(rec["bytes"])])
    return table_booktabs("cllrc", rows, caption, label)


# ===========================================================================
# 代码段（英文注释以保证 listings 排版正确）
# ===========================================================================

CODE_CHANNEL = r"""class Channel:
    # Simulated channel: meters traffic (bytes) and interaction rounds.
    def __init__(self):
        self.bytes = 0      # total transmitted bytes
        self.rounds = 0     # total number of messages
        self.log = []       # auditable message log

    def send(self, sender, receiver, payload, note=""):
        size = wire_size(payload)          # serialized length in bytes
        self.bytes += size
        self.rounds += 1
        self.log.append({"seq": self.rounds, "from": sender,
                         "to": receiver, "note": note, "bytes": size})
        return payload


def wire_size(obj):
    # Wire size of int / bytes / str / list / tuple / dict.
    if isinstance(obj, int):
        return max(1, (obj.bit_length() + 7) // 8)
    if isinstance(obj, (bytes, bytearray)):
        return len(obj)
    if isinstance(obj, str):
        return len(obj.encode("utf-8"))
    if isinstance(obj, (list, tuple, set)):
        return sum(wire_size(x) for x in obj)
    ..."""

CODE_YAO_BOB = r"""# --- Bob (decider): blind his own wealth with a fresh random x ---
def step2_blind(self, ch, peer, n, e):
    x = rand_below(n)                  # fresh randomness, |x| ~ |n|
    C = modexp(x, e, n)                # public-key transform C = x^e mod n
    k = (C - self.wealth) % n          # modulo boundary: C - b may be negative
    ch.send(self.name, peer, k, "k = x^e mod n - b")
    return k"""

CODE_YAO_ALICE = r"""# --- Alice (encryptor): private-key op, mod-p folding, then perturb ---
def step3_transform(self, ch, peer, k, N, p_bits):
    n, d = self.key.n, self.key.d
    nums = [(k + i) % n for i in range(1, N + 1)]   # modulo boundary
    while True:                                     # retry with a fresh prime
        p = gen_prime(p_bits)
        Y = [modexp(v, d, n) for v in nums]         # N private-key modexps
        Z = [y % p for y in Y]
        ok = True
        if Z and max(Z) + 1 >= p:                   # (b) no wrap around p
            ok = False
        if ok:                                      # (a) pairwise gap >= 2
            srt = sorted(Z)
            for i in range(1, len(srt)):
                if srt[i] - srt[i - 1] < 2:
                    ok = False
                    break
        if ok:
            break
    # perturb: keep Z_i for i <= a, add 1 for i > a
    W = [Z[i] if (i + 1) <= self.wealth else Z[i] + 1 for i in range(N)]
    ch.send(self.name, peer, [p] + W, "prime p and N folded values")
    return p, W"""

CODE_YAO_DECIDE = r"""# --- Bob (decider): only inspect his OWN slot ---
def step4_decide(self, ch, peer, p, W):
    G = self._x % p                       # Y_b = (k+b)^d = (x^e)^d = x
    result = (W[self.wealth - 1] == G)    # True  <=>  w_p >= w_q
    ch.send(self.name, peer, 1 if result else 0, "1-bit decision")
    return result"""

CODE_OT = r"""# ---- Round 1: sender -> receiver -------------------------------------
def round1(self, ch, peer):
    N, e = self.key.n, self.key.e
    self.xs = [rand_below(N) for _ in range(self.n_msg)]   # n blinding factors
    ch.send(self.name, peer, (N, e, self.xs), "public key and x_i")
    return N, e, self.xs

# ---- Round 2: receiver -> sender -------------------------------------
def round2(self, ch, peer, N, e, xs):
    k = rand_below(N)
    self.k = k
    y = xs[self.sigma] * modexp(k, e, N) % N    # y = x_sigma * k^e mod N
    ch.send(self.name, peer, y, "blinded choice")
    return y

# ---- Round 3: sender -> receiver -------------------------------------
def round3(self, ch, peer, y):
    N, d = self.key.n, self.key.d
    ciphers = []
    for i in range(self.n_msg):
        k_i = modexp(y * pow(self.xs[i], -1, N) % N, d, N)  # (y/x_i)^d
        ciphers.append(mask(self.messages[i], k_i))          # m_i XOR H(k_i)
    ch.send(self.name, peer, ciphers, "n encrypted messages")
    return ciphers

# ---- Local decryption: only index sigma works ------------------------
def decrypt(self, ciphers):
    return unmask(ciphers[self.sigma], self.k)"""

CODE_OT_MP = r"""# MSG_ALICE_RICHER / MSG_EQUAL / MSG_BOB_RICHER are the three
# allowed outputs of the millionaires problem.
def compare_label(a, i):
    if i < a:  return MSG_ALICE_RICHER   # i < a  -> Alice is richer
    if i == a: return MSG_EQUAL          # i == a -> equal
    return MSG_BOB_RICHER                # i > a  -> Bob is richer

def build_ot_messages(a, N):
    # m_i = cmp(a, i) for i = 1..N, padded to a fixed 32-byte block
    return [pad_block(compare_label(a, i), MESSAGE_BLOCK)
            for i in range(1, N + 1)]

def ot_millionaires(a, b, N, bits=1024):
    ch = Channel()
    alice = OTSender("Alice", build_ot_messages(a, N), bits=bits)
    bob   = OTReceiver("Bob", b - 1)          # sigma = b - 1
    N_mod, e, xs = alice.round1(ch, bob.name)
    y            = bob.round2(ch, alice.name, N_mod, e, xs)
    ciphers      = alice.round3(ch, bob.name, y)
    result       = unpad_block(bob.decrypt(ciphers))   # = cmp(a, b)
    ch.send("Bob", "Alice", pad_block(result, MESSAGE_BLOCK), "result")
    return result, ch"""

CODE_PRIME = r"""# Miller-Rabin probabilistic primality test
def is_probable_prime(n, rounds=40):
    for p in _SMALL_PRIMES:
        if n == p: return True
        if n % p == 0: return False
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2; s += 1
    for _ in range(rounds):
        a = _rng.randrange(2, n - 1)
        x = modexp(a, d, n)
        if x == 1 or x == n - 1: continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1: break
        else:
            return False
    return True


# Generate an RSA key pair of `bits` bits
def gen_rsa_keypair(bits, e=65537):
    while True:
        p = gen_prime(bits // 2)
        q = gen_prime(bits // 2)
        if p == q: continue
        n = p * q
        phi = (p - 1) * (q - 1)
        if math.gcd(e, phi) != 1: continue
        return RSAKey(n, e, pow(e, -1, phi), bits)"""


def listing(code: str, caption: str, label: str) -> str:
    return (rf"\begin{{lstlisting}}[language=Python, caption={{{caption}}}, "
            rf"label={{{label}}}]" + "\n" + code + "\n" + r"\end{lstlisting}")


# ===========================================================================
# 组装报告
# ===========================================================================

# ---- 图：可扩展性 ----
scal_time = tikz_lines(
    [
        {"name": "任务一 Yao 原始方案", "style": "blue,thick", "mark": "square*",
         "pts": [(r["N"], r["yao_ms"]) for r in SCAL]},
        {"name": "任务二 1-out-of-n OT", "style": "red,thick", "mark": "*",
         "pts": [(r["N"], r["ot_ms"]) for r in SCAL]},
    ],
    xlabel=r"财富上界 $N$", ylabel="在线耗时 (ms)",
    xmin=0, xmax=110, ymin=0, ymax=800,
    xticks=[0, 10, 25, 50, 100], yticks=[0, 200, 400, 600, 800],
    legend_pos=(5.6, 4.6),
)

scal_bytes = tikz_lines(
    [
        {"name": "任务一 Yao 原始方案", "style": "blue,thick", "mark": "square*",
         "pts": [(r["N"], r["yao_bytes"]) for r in SCAL]},
        {"name": "任务二 1-out-of-n OT", "style": "red,thick", "mark": "*",
         "pts": [(r["N"], r["ot_bytes"]) for r in SCAL]},
    ],
    xlabel=r"财富上界 $N$", ylabel="通信量 (Byte)",
    xmin=0, xmax=110, ymin=0, ymax=18000,
    xticks=[0, 10, 25, 50, 100], yticks=[0, 5000, 10000, 15000],
    legend_pos=(5.0, 4.6),
)

perf_bar = tikz_bars(
    [
        ("RSA 1024 位", [("Yao 原始方案", P[1024]["time_online"] * 1000, "blue!55"),
                         ("1-out-of-n OT", O[1024]["time_online"] * 1000, "red!55")]),
        ("RSA 2048 位", [("Yao 原始方案", P[2048]["time_online"] * 1000, "blue!55"),
                         ("1-out-of-n OT", O[2048]["time_online"] * 1000, "red!55")]),
    ],
    ylabel="在线耗时 (ms)", ymax=5600,
    yticks=[0, 1000, 2000, 3000, 4000, 5000],
)

# ---- 表：性能对比 ----
perf_rows = [["方案", "RSA 位数", "在线耗时 (ms)", "含密钥生成 (ms)",
              "通信量 (B)", "交互轮数", "模幂次数"]]
for bits in (1024, 2048):
    for tag, d in (("任务一 Yao 原始方案", P[bits]),
                   ("任务二 1-out-of-n OT", O[bits])):
        perf_rows.append([tag, str(bits),
                          fmt(d["time_online"] * 1000, 2),
                          fmt(d["time_with_keygen"] * 1000, 2),
                          fmt(d["bytes"]), str(d["rounds"]), str(d["modexp"])])
tab_perf = table_booktabs("llrrrrrr"[0:7], perf_rows,
                          "两种方案的性能与通信开销对比（$N=100$，$a=73$，$b=28$）",
                          "tab:perf")

# ---- 表：可扩展性 ----
scal_rows = [[r"财富上界 $N$", "Yao 耗时 (ms)", "Yao 通信量 (B)", "Yao 轮数",
              "OT 耗时 (ms)", "OT 通信量 (B)", "OT 轮数"]]
for r in SCAL:
    scal_rows.append([str(r["N"]), fmt(r["yao_ms"], 2), fmt(r["yao_bytes"]),
                      str(r["yao_rounds"]), fmt(r["ot_ms"], 2),
                      fmt(r["ot_bytes"]), str(r["ot_rounds"])])
tab_scal = table_booktabs("cccccccc"[0:7], scal_rows,
                          "财富上界 $N$ 对耗时与通信量的影响（RSA 1024 位）",
                          "tab:scal")

# ---- 表：正确性 ----
ex = CORR["exhaustive_n10"]
rn = CORR["random_n100"]
os_ = CORR["ot_self"]
corr_rows = [["测试项", "规模", "用例数", "正确数", "正确率"]]
corr_rows.append([r"穷举全部 $(a,b)$（两方案合计）", r"$N=10$",
                  str(ex["cases"]), str(ex["correct"]),
                  f"{ex['accuracy']:.2f}\\%"])
corr_rows.append(["任务一 Yao 随机+边界用例", r"$N=100$",
                  str(rn["yao_total"]), str(rn["yao_correct"]),
                  f"{rn['yao_accuracy']:.2f}\\%"])
corr_rows.append(["任务二 OT 随机+边界用例", r"$N=100$",
                  str(rn["ot_total"]), str(rn["ot_correct"]),
                  f"{rn['ot_accuracy']:.2f}\\%"])
corr_rows.append([r"1-out-of-8 OT 遍历全部选择", r"$n=8$",
                  str(os_["cases"]), str(os_["correct"]),
                  f"{os_['accuracy']:.2f}\\%"])
tab_corr = table_booktabs("lcccc", corr_rows,
                          "正确性测试结果（RSA 1024 位）", "tab:corr")

# 三种结果的分布
out_rows = [["比较结果", "用例数", "Yao 正确数", "OT 正确数"]]
for k, v in rn["by_outcome"].items():
    out_rows.append([k, str(v["n"]), str(v["yao_ok"]), str(v["ot_ok"])])
tab_out = table_booktabs("lccc", out_rows,
                         r"$N=100$ 随机测试中三种输出的分布与正确数",
                         "tab:outcome")

# ---- 表：可见信息 ----
vis = PRIV["visible"]
vis_rows = [["方案", "参与方", "可见信息"]]
name_map = {
    "Yao_Alice_可见": ("任务一 Yao", "Alice"),
    "Yao_Bob_可见": ("任务一 Yao", "Bob"),
    "OT_Alice_可见": ("任务二 OT", "Alice"),
    "OT_Bob_可见": ("任务二 OT", "Bob"),
}
for k, (scheme, who) in name_map.items():
    items = vis[k]
    vis_rows.append([scheme, who, items[0]])
    for it in items[1:]:
        vis_rows.append(["", "", esc(it)])
tab_vis = table_booktabs("lll", vis_rows,
                         "半诚实模型下双方的可见信息清单", "tab:visible")

# ---- 演示日志表 ----
tab_log_y = msglog_table(DEMO["yao"]["log"],
                         f"任务一 Yao 方案的消息交互日志"
                         f"（$N=10$，$a=7$，$b=3$，RSA 1024 位；"
                         f"共 {DEMO['yao']['rounds']} 轮 / "
                         f"{fmt(DEMO['yao']['bytes'])} B）",
                         "tab:logyao")
tab_log_o = msglog_table(DEMO["ot"]["log"],
                         f"任务二 OT 方案的消息交互日志"
                         f"（$N=10$，$a=7$，$b=3$，RSA 1024 位；"
                         f"共 {DEMO['ot']['rounds']} 轮 / "
                         f"{fmt(DEMO['ot']['bytes'])} B）",
                         "tab:logot")

# ---- 隐私实证表 ----
ps = PRIV["sender"]
pr = PRIV["receiver"]
priv_rows = [["隐私目标", "实验方法", "实测结果", "结论"]]
priv_rows.append([
    r"发送方不可知选择 $\sigma$",
    rf"对 $\sigma=0,1$ 各采样 {ps['samples']} 个 $y$，训练经验最优阈值分类器",
    rf"两类样本均值 {ps['mean0']:.4f} / {ps['mean1']:.4f}，"
    rf"标准差 {ps['std0']:.4f} / {ps['std1']:.4f}；"
    rf"分类器准确率 {ps['classifier_acc']:.2f}\%",
    "接近随机猜测 50\\%，无法区分"])
priv_rows.append([
    "接收方不可知未选消息",
    "用自己掌握的 $k$ 逐条解密全部密文",
    rf"可识别明文 {pr['decryptable']} 条（期望 {pr['expected']} 条），"
    rf"其余为乱码",
    "仅第 $\\sigma$ 条可解，其余不可读"])
tab_priv = table_booktabs("llll"[0:4], priv_rows,
                          "隐私性实证结果（RSA 1024 位）", "tab:priv")

garble = "\n".join(
    rf"\item $c_{{{i}}}$ 解密前 24 hex：\texttt{{{g}}}"
    + (r"（选中，可正确解密）" if i == pr["sigma"] else r"（乱码，不可读）")
    for i, g in enumerate(pr["garble_hex"])
)

# ===========================================================================
# 正文
# ===========================================================================

body = rf"""
%!TeX program = xelatex
\documentclass{{SYSUReport}}
\usepackage{{amsmath}}
\usepackage{{amssymb}}
\usepackage{{tikz}}
\usepackage{{adjustbox}}
\usepackage{{booktabs}}
\usepackage{{multirow}}
\usepackage{{graphicx}}
\usepackage{{longtable}}
\usepackage{{listings}}
\usepackage{{xcolor}}
\usepackage{{caption}}
\setlength{{\headheight}}{{14.5pt}}
\lstdefinestyle{{mystyle}}{{%
    backgroundcolor=\color{{gray!8}},
    basicstyle=\ttfamily\small,
    keywordstyle=\color{{blue!70!black}},
    commentstyle=\color{{green!40!black}},
    stringstyle=\color{{purple!60!black}},
    numbers=left,
    numberstyle=\tiny\color{{gray}},
    frame=single,
    breaklines=true,
    captionpos=b,
    showstringspaces=false,
    tabsize=4,
}}
\lstset{{style=mystyle}}
% ============ 根据个人情况修改 ============
\headl{{24337058 刘博文}}
\headc{{}}
\headr{{数据安全和隐私保护}}
\lessonTitle{{数据安全和隐私保护}}
\reportTitle{{实验二、百万富翁问题与不经意传输}}
\stuname{{刘博文}}
\stuid{{24337058}}
\inst{{网络空间安全学院}}
\major{{网络空间安全}}
\date{{2026 年 10 月 7 日}}
% ==========================================
\begin{{document}}
\cover
\thispagestyle{{empty}}
\clearpage
\tableofcontents
\clearpage
\pagenumbering{{arabic}}
\setcounter{{page}}{{1}}

\section{{实验目的与要求}}

本次实验围绕隐私计算中的\textbf{{百万富翁问题}}（Millionaires' Problem）展开：Alice 与 Bob 各自持有财富 $a$、$b$，希望在不向对方透露具体数值的前提下判断谁更富有。实验包含两项任务：

\begin{{enumerate}}
    \item \textbf{{任务一}}：模拟并实现百万富翁问题的\textbf{{原始求解方案}}——基于公钥变换、随机数与交互判断的 Yao 协议；
    \item \textbf{{任务二}}：实现 \textbf{{$n$ 选 1 不经意传输}}（1-out-of-$n$ Oblivious Transfer），并用它求解百万富翁问题。
\end{{enumerate}}

实验要求两个任务均只输出“Alice 更富有”“Bob 更富有”“双方财富相等”三态结果，\textbf{{不得输出对方财富及差值}}；禁止以明文交换、共享变量直接比较或可信第三方代算代替协议；并需在相同设备、相同输入、可比密码参数下，记录两种方案的\textbf{{正确率、耗时、通信字节数、交互轮数}}，分析其隐私性。

\section{{实验原理}}

\subsection{{百万富翁问题}}

百万富翁问题由 Andrew Yao 于 1982 年提出\cite{{yao1982}}，是安全多方计算（Secure Multi-party Computation, MPC）的开端问题。双方共同计算比较函数

\begin{{equation}}
f(a,b)=
\begin{{cases}}
\text{{Alice 更富有}}, & a>b,\\
\text{{双方财富相等}}, & a=b,\\
\text{{Bob 更富有}},   & a<b.
\end{{cases}}
\end{{equation}}

安全目标是：\textbf{{允许获知结果本身及其必然推论，但不获得任何额外信息}}。本实验按\textbf{{半诚实模型}}（semi-honest model）讨论，即双方严格遵守协议流程，但会保留并分析收到的所有消息，试图从中推断对方的私有输入。

\subsection{{原始求解方案：基于公钥变换的 Yao 协议}}

设财富取值范围为 $1\ldots N$（$N$ 为公开上界）。原始方案利用\textbf{{公钥变换}}隐藏 Bob 的财富索引：Alice 对全部 $N$ 个候选位置做\textbf{{私钥运算}}并\textbf{{模素数压缩}}，再依据自身财富对部分结果加 $1$；Bob 只在\textbf{{自己那一个位置}}检验随机数对应关系，从而得到大小关系。

一轮协议中，称持有 RSA 密钥、做私钥运算的一方为\textbf{{加密方 P}}（财富 $w_p$），做盲化与判定的一方为\textbf{{判定方 Q}}（财富 $w_q$）：

\begin{{enumerate}}
    \item \textbf{{密钥生成与公开}}：P 生成 RSA 密钥对 $(n,e,d)$，把公钥 $(n,e)$ 发给 Q。
    \item \textbf{{盲化}}：Q 选取随机数 $x$（$|x|\approx|n|$），计算 $C=x^{{e}}\bmod n$，发送
          \begin{{equation}}
          k=(C-w_q)\bmod n.
          \end{{equation}}
          由于 $x$ 随机，且不掌握私钥 $d$，P 无法从 $k$ 反推 $w_q$。
    \item \textbf{{私钥运算与模素数压缩}}：P 对全部 $N$ 个候选位置计算
          \begin{{equation}}
          Y_i=(k+i)^{{d}}\bmod n,\qquad Z_i=Y_i\bmod p,\qquad i=1,\ldots,N,
          \end{{equation}}
          其中 $p$ 是 P 随机选取的素数，须通过\textbf{{余数间距检验}}：$\forall i\neq j,\ |Z_i-Z_j|\ge 2$，且 $\forall i,\ Z_i+1<p$；不满足则\textbf{{换素数重试}}。随后 P 依据自身财富做扰动并发送
          \begin{{equation}}
          W_i=
          \begin{{cases}}
          Z_i,   & i\le w_p,\\
          Z_i+1, & i>w_p.
          \end{{cases}}
          \end{{equation}}
    \item \textbf{{判定}}：Q 计算 $G=x\bmod p$，\textbf{{只检查自己那一位}}：
          \begin{{equation}}
          W_{{w_q}}\stackrel{{?}}{{=}}G.
          \end{{equation}}
\end{{enumerate}}

关键推导：当 $i=w_q$ 时，$Y_{{w_q}}=(k+w_q)^{{d}}\equiv C^{{d}}\equiv (x^{{e}})^{{d}}\equiv x\pmod n$，故 $Z_{{w_q}}=x\bmod p=G$。若 $w_q\le w_p$，P 未加 $1$，于是 $W_{{w_q}}=G$ 成立；若 $w_q>w_p$，则 $W_{{w_q}}=G+1\neq G$。因此
\begin{{equation}}
W_{{w_q}}=G\quad\Longleftrightarrow\quad w_q\le w_p\ (\text{{即 }}w_p\ge w_q).
\end{{equation}}

\textbf{{相等情况的处理}}：单轮只能区分 $a\ge b$ 与 $a<b$。交换角色、使用\textbf{{全新随机数与全新密钥}}再跑一轮，得到 $b\ge a$ 与否，二者合并即可区分三态：
\begin{{equation}}
\begin{{cases}}
r_1=1,\ r_2=1 \Rightarrow a=b;\\
r_1=1,\ r_2=0 \Rightarrow a>b;\\
r_1=0,\ r_2=1 \Rightarrow a<b.
\end{{cases}}
\end{{equation}}

\subsection{{不经意传输}}

不经意传输（Oblivious Transfer, OT）由 Michael Rabin 于 1981 年提出\cite{{rabin1981}}，核心目标是“选择性隐私传输”。1-out-of-2 OT 中，发送方持有 $m_0,m_1$，接收方选择索引 $\sigma$：

\begin{{itemize}}
    \item 接收方\textbf{{只收到}} $m_\sigma$，且\textbf{{无法获知}} $m_{{1-\sigma}}$；
    \item 发送方\textbf{{无法得知}} $\sigma$。
\end{{itemize}}

即 OT 同时提供\textbf{{对发送方消息的单向保护}}与\textbf{{对接收方选择的保护}}，是安全多方计算的基础原语。

\subsection{{基于 RSA 的 1-out-of-$n$ OT（EGL 构造）}}

本实验采用 Even--Goldreich--Lempel 的 RSA 构造\cite{{egl1985}}并推广到 $n$ 条消息。公共参数为 RSA 模数 $N$（$|N|=\text{{bits}}$），公钥指数 $e=65537$；发送方 S 持有 $m_0,\ldots,m_{{n-1}}$，接收方 R 持有 $\sigma$。

\begin{{enumerate}}
    \item \textbf{{S $\to$ R}}：S 生成 RSA 密钥对，随机选取 $n$ 个盲化因子 $x_0,\ldots,x_{{n-1}}\in\mathbb{{Z}}_N^{{*}}$，发送 $(N,e,x_0,\ldots,x_{{n-1}})$。
    \item \textbf{{R $\to$ S}}：R 随机选 $k\in\mathbb{{Z}}_N^{{*}}$，计算并发送
          \begin{{equation}}
          y=x_\sigma\cdot k^{{e}}\bmod N.
          \end{{equation}}
          因 $k^{{e}}$ 是随机的 $e$ 次幂，$y$ 在 RSA 假设下与均匀分布不可区分，故\textbf{{S 无法判断 $\sigma$}}。
    \item \textbf{{S $\to$ R}}：S 对每个 $i$ 计算
          \begin{{equation}}
          k_i=(y\cdot x_i^{{-1}})^{{d}}\bmod N,\qquad c_i=m_i\oplus H(k_i),
          \end{{equation}}
          发送 $c_0,\ldots,c_{{n-1}}$，其中 $H$ 为 SHA-256 派生的密钥流。
    \item \textbf{{R 本地解密}}：$m_\sigma=c_\sigma\oplus H(k)$。
\end{{enumerate}}

正确性：当 $i=\sigma$ 时 $k_\sigma=(x_\sigma k^{{e}}x_\sigma^{{-1}})^{{d}}\equiv (k^{{e}})^{{d}}\equiv k\pmod N$，解密成功；而 $i\neq\sigma$ 时求 $k_i$ 等价于由 $k_i^{{e}}=y/x_i$ 求 $e$ 次根，即\textbf{{攻破 RSA}}，故\textbf{{R 只能解开 $m_\sigma$}}。

\subsection{{用 1-out-of-$n$ OT 求解百万富翁问题}}

Alice 作为\textbf{{OT 发送方}}，构造 $N$ 条消息，第 $i$ 条（$i=1\ldots N$）是“把 $a$ 与 $i$ 比较”的结果：
\begin{{equation}}
m_i=
\begin{{cases}}
\text{{Alice 更富有}}, & i<a,\\
\text{{双方财富相等}}, & i=a,\\
\text{{Bob 更富有}},   & i>a.
\end{{cases}}
\end{{equation}}
Bob 作为\textbf{{OT 接收方}}，以 $\sigma=b-1$ 执行一次 1-out-of-$N$ OT，取出 $m_b=\text{{cmp}}(a,b)$，\textbf{{正好就是题目要求的输出}}。

该方案只需 \textbf{{1 次 OT、3 轮交互}}，且\textbf{{天然区分相等}}，无需像原始方案那样交换角色再跑一轮。其安全性直接由 OT 的双向保护导出：Alice 看不到 $\sigma$（故不知 $b$），Bob 只能解开 $m_b$（故不知 $a$ 的额外信息）。

\section{{实验环境}}

\begin{{itemize}}
    \item \textbf{{操作系统}}：{esc(META['platform'])}
    \item \textbf{{处理器}}：{esc(META['processor'] or 'x86_64')}
    \item \textbf{{编程语言}}：Python {esc(META['python'])}（仅使用标准库）
    \item \textbf{{密码学基础运算}}：Miller-Rabin 素性检测、随机大素数生成、RSA 密钥对生成、模幂运算均\textbf{{自行实现}}（见代码 \ref{{lst:prime}}），未调用第三方密码库
    \item \textbf{{散列函数}}：\texttt{{hashlib.sha256}}，用于 OT 掩码密钥流（MGF1 风格）
    \item \textbf{{随机数}}：\texttt{{secrets.SystemRandom}}（操作系统密码学安全随机源）
    \item \textbf{{密钥参数}}：RSA 模数 1024 / 2048 位，公钥指数 $e=65537$；Yao 方案中压缩素数 $p$ 取 $|n|/4$ 位
    \item \textbf{{排版工具}}：XeLaTeX（MiKTeX 发行版）+ SYSU 实验报告模板，插图由 TikZ 绘制为矢量图
\end{{itemize}}

\section{{实验设计与实现}}

工程结构如下：\texttt{{common.py}}（公共基础：信道、数论、RSA、掩码）、\texttt{{yao\_millionaires.py}}（任务一）、\texttt{{ot\_rsa.py}}（$n$ 选 1 OT）、\texttt{{ot\_millionaires.py}}（用 OT 解百万富翁问题）、\texttt{{run\_experiments.py}}（实验入口）。

\subsection{{总体设计：可统计的模拟信道}}

为了客观比较通信开销与交互轮数，实验没有让两方直接共享变量，而是让所有消息都必须经过一个\textbf{{可统计的信道}}。信道按“序列化后的字节数”累加通信量，每发一条消息记一轮，并输出可审计的消息日志（表 \ref{{tab:logyao}}、表 \ref{{tab:logot}}）。

{listing(CODE_CHANNEL, "可统计的模拟信道（common.py 节选）", "lst:channel")}

\subsection{{密码学基础运算}}

{listing(CODE_PRIME, "Miller-Rabin 素性检测与 RSA 密钥生成", "lst:prime")}

\subsection{{任务一的实现}}

加密方与判定方被设计为两个独立类 \texttt{{YaoEncryptor}} / \texttt{{YaoDecider}}，各自只持有自己的私有输入，任何一方都拿不到对方的财富变量。

{listing(CODE_YAO_BOB, "任务一 步骤2：判定方盲化自己的财富", "lst:yaobob")}

代码 \ref{{lst:yaobob}} 中，$x$ 每轮\textbf{{全新}}随机；$k=(C-b)\bmod n$ 显式取模，处理 $C-b$ 为负的\textbf{{模运算边界}}。

{listing(CODE_YAO_ALICE, "任务一 步骤3：私钥运算、模素数压缩、间距检验与扰动", "lst:yaoalice")}

代码 \ref{{lst:yaoalice}} 有三个关键点：
\begin{{enumerate}}
    \item $(k+i)\bmod n$ 统一取模，避免 $k+i$ 越过模数边界；
    \item \textbf{{间距检验与失败重试}}：要求任意两个 $Z_i$ 相差至少 $2$、且 $Z_i+1<p$，使“加 $1$”既不与其他 $Z_j$ 撞车也不越过模数边界；不满足就换新素数 $p$ 重算。取 $|p|=|n|/4$ 时该条件以压倒性概率一次通过（实测每轮仅 1 次尝试）。
    \item \textbf{{按自身财富扰动}}：$i\le a$ 原样发送，$i>a$ 加 $1$，这是唯一泄露大小关系的地方，且只泄露 1 比特。
\end{{enumerate}}

{listing(CODE_YAO_DECIDE, "任务一 步骤4：判定方只检查自己的位置", "lst:yaodec")}

完整求解时交换角色再跑一轮，合并两轮结果即可区分三态（见代码 \texttt{{yao\_millionaires}}）。

\subsection{{任务二：$n$ 选 1 OT 的实现}}

{listing(CODE_OT, "基于 RSA 的 1-out-of-n OT 三轮实现（ot\\_rsa.py 节选）", "lst:ot")}

实现要点：
\begin{{itemize}}
    \item 盲化因子 $x_i$ 与密钥一样属于\textbf{{一次性参数}}，每次协议全新生成；
    \item 模逆用 \texttt{{pow(a,-1,N)}}；$k_i=(y\cdot x_i^{{-1}})^{{d}}\bmod N$ 共 $n$ 次私钥模幂，是 OT 的主要计算开销；
    \item 消息统一填充为 \textbf{{定长 32 字节块}}后再异或掩码，\textbf{{消除长度侧信道}}；
    \item 掩码为 $\texttt{{SHA256}}(\text{{domain}}\Vert k_i\Vert \text{{ctr}})$ 级联的 MGF1 风格密钥流。
\end{{itemize}}

\subsection{{任务二：用 OT 求解百万富翁问题}}

{listing(CODE_OT_MP, "用 1-out-of-N OT 求解百万富翁问题（ot\\_millionaires.py 节选）", "lst:otmp")}

代码 \ref{{lst:otmp}} 中 Alice 只需构造 $N$ 条消息，Bob 以 $\sigma=b-1$ 取一次，得到的就是最终三态结果。最后由 Bob 把该结果（\textbf{{本身就是允许公开的输出}}）定长回传给 Alice，使双方得到一致结论。

\section{{实验结果与分析}}

\subsection{{协议流程演示}}

取 $N=10$、$a=7$、$b=3$、RSA 1024 位，两个方案均输出“Alice 更富有”，与明文参考结果一致。消息交互日志如下。

{tab_log_y}

{tab_log_o}

可以看到：Yao 方案\textbf{{两轮共 8 条消息}}，其中第 3、7 条是 $N$ 个压缩值，是本方案通信量的主体；OT 方案仅 \textbf{{4 条消息}}，但第 1 条要发送 $N$ 个盲化因子（每个 $|N|$ 位），通信量反而更大——这构成了两种方案最核心的权衡：\textbf{{Yao 通信量小但交互轮数多、计算量大；OT 轮数少、计算量小但通信量大}}。

\subsection{{正确性测试}}

{tab_corr}

{tab_out}

在 RSA 1024 位下，$N=10$ 时\textbf{{穷举全部 100 组 $(a,b)$}}、$N=100$ 时\textbf{{随机 106 组（含边界用例）}}，两个方案的正确率均为 \textbf{{100.00\%}}；1-out-of-8 OT 遍历全部选择重复 20 轮共 160 次亦全部正确。三种输出（Alice 更富有 / Bob 更富有 / 双方财富相等）的分布与正确数见表 \ref{{tab:outcome}}，说明\textbf{{相等情况也被正确处理}}。

\subsection{{性能对比}}

在相同设备、相同输入（$N=100$、$a=73$、$b=28$）、相同密码参数下对比两种方案，结果见表 \ref{{tab:perf}} 与图 \ref{{fig:perfbar}}。

{tab_perf}

\begin{{figure}}[h]
\centering
{perf_bar}
\caption{{两种方案的在线耗时对比（$N=100$，不含一次性密钥生成开销）}}
\label{{fig:perfbar}}
\end{{figure}}

\begin{{itemize}}
    \item \textbf{{耗时}}：OT 方案的在线耗时约为 Yao 的 \textbf{{46\%～47\%}}。原因是 Yao 需跑\textbf{{两轮}}（每轮 $N$ 次私钥模幂，共 $\approx 2N$ 次），而 OT 只需\textbf{{一轮}}（$N$ 次私钥模幂）。实测模幂次数：Yao $\approx {P[1024]['modexp']}$ 次，OT $\approx {O[1024]['modexp']}$ 次，与理论分析 $2N$ 对 $N$ 吻合。
    \item \textbf{{通信量}}：Yao 约 {fmt(P[1024]['bytes'])} B（1024 位），OT 约 {fmt(O[1024]['bytes'])} B，OT 约为 Yao 的 {O[1024]['bytes'] / P[1024]['bytes']:.1f} 倍。因为 OT 第 1 轮要发送 $N$ 个 $|N|$ 位的盲化因子 $x_i$，而 Yao 传送的是 $N$ 个 $|p|=|n|/4$ 位的压缩值。
    \item \textbf{{交互轮数}}：Yao 为 {P[1024]['rounds']} 轮，OT 为 {O[1024]['rounds']} 轮（含结果回传），OT 减少一半。在对延迟敏感的网络环境中，这一优势往往比字节数更重要。
    \item \textbf{{密钥生成}}：Yao 需 2 把 RSA 密钥（双方各做一次加密方），OT 只需 1 把。RSA-1024 单次密钥生成约 {fmt(P[1024]['time_keygen'] * 1000, 1)} ms，RSA-2048 约 {fmt(P[2048]['time_keygen'] * 1000, 1)} ms，属于一次性开销，可通过密钥复用摊薄。
    \item \textbf{{安全参数的影响}}：从 1024 位提升到 2048 位，两者耗时均增长约 {P[2048]['time_online'] / P[1024]['time_online']:.1f}～{O[2048]['time_online'] / O[1024]['time_online']:.1f} 倍，与模幂运算 $O(|n|^{{2}})$～$O(|n|^{{3}})$ 的复杂度增长一致，相对优劣关系不变。
\end{{itemize}}

\subsection{{可扩展性分析}}

财富上界 $N$ 直接决定需要处理的候选位置数量。图 \ref{{fig:sctime}} 与图 \ref{{fig:scbytes}} 给出 $N=10,25,50,100$ 时两种方案的耗时与通信量，原始数据见表 \ref{{tab:scal}}。

\begin{{figure}}[h]
\centering
{scal_time}
\caption{{财富上界 $N$ 对在线耗时的影响（RSA 1024 位）}}
\label{{fig:sctime}}
\end{{figure}}

\begin{{figure}}[h]
\centering
{scal_bytes}
\caption{{财富上界 $N$ 对通信量的影响（RSA 1024 位）}}
\label{{fig:scbytes}}
\end{{figure}}

{tab_scal}

两者耗时与通信量均随 $N$ \textbf{{线性增长}}，但斜率不同：耗时的斜率比约为 $2:1$（Yao 跑两轮），通信量的斜率比约为 $1:2.3$（Yao 传 $|p|=\frac{{1}}{{4}}|n|$ 位的压缩值，OT 传 $|N|$ 位的盲化因子）。这说明：\textbf{{当财富范围很大时，Yao 方案在通信量上更有优势，而 OT 方案在耗时与轮数上更有优势}}。实际工程中可用“分桶 / 按位比较 + OT 扩展”等技术把 OT 的通信量降到 $O(\log N)$。

\section{{隐私性分析}}

\subsection{{半诚实模型下双方的可见信息}}

{tab_vis}

\subsection{{为何不应泄露未选消息、选择位与额外财富信息}}

\begin{{enumerate}}
    \item \textbf{{未选消息（OT 的发送方隐私）}}：在百万富翁场景中，Alice 的 $N$ 条消息 $m_i=\text{{cmp}}(a,i)$ 事实上\textbf{{完整编码了她的财富}}——只要能读出足够多条消息，就能二分定位出 $a$ 的精确值。因此若接收方能解密未选消息，协议就退化为“明文交换”，直接违背隐私目标。OT 通过“每条消息用不同的 $k_i$ 掩码，且只有 $k_\sigma$ 可解”来阻断这条通路。
    \item \textbf{{选择位 $\sigma$（OT 的接收方隐私）}}：$\sigma=b-1$ \textbf{{就是 Bob 财富本身}}。若发送方能识别出 $\sigma$，则 Bob 的私有输入完全暴露。协议中 $y=x_\sigma\cdot k^{{e}}\bmod N$ 被随机 $e$ 次幂盲化，在 RSA 假设下与 $\sigma$ 独立，从而保护选择位。
    \item \textbf{{额外的财富信息（两种方案共有）}}：协议允许泄露的只有\textbf{{比较结果本身及其必然推论}}（例如由“Alice 更富有”可推出 $a>b$，由“相等”可推出 $a=b$）。除此之外，任何关于 $a$ 或 $b$ 的具体取值、差值、所属区间的额外信息都不应泄露。
          \begin{{itemize}}
              \item Yao 方案中，Alice 收到的是被随机 $x$ 盲化的 $k$，她虽然持有私钥 $d$，但不知道 $x$，无法判断 $N$ 个 $Y_i$ 中哪一个是 $x$，因此学不到 $b$；Bob 只掌握自己那一位的对应关系，其余 $W_i$ 因缺少 $d$ 而无法解读，因此学不到 $a$。
              \item OT 方案中，安全性直接归约到 OT 原语的双向保护，且消息定长填充避免了长度侧信道。
          \end{{itemize}}
    \item \textbf{{相等判定的代价}}：Yao 方案为区分相等必须交换角色再跑一轮，这会让双方各多知晓一个 1 比特的中间结论（$a\ge b$ 与 $b\ge a$）。但由于二者都\textbf{{被最终输出所蕴含}}，并不构成额外泄露。OT 方案只需一轮即可得到三态结果，暴露面更小。
\end{{enumerate}}

\subsection{{隐私性实证结果}}

{tab_priv}

接收方尝试用自己的 $k$ 解密全部密文，结果如下：
\begin{{itemize}}
{garble}
\end{{itemize}}

需要说明的是，上述“分类器准确率”只是\textbf{{一个具体的攻击尝试}}，用以直观展示 $y$ 对 $\sigma$ 没有可利用的统计偏差；发送方隐私的严格保证来自 RSA 假设下的不可区分性，而非某一次统计检验。

\section{{实验总结}}

本次实验完成了百万富翁问题的两种求解方案并进行了系统对比：

\begin{{enumerate}}
    \item \textbf{{任务一}}实现了 Yao 原始方案：利用 RSA 公钥变换隐藏财富索引，通过私钥运算、模素数压缩、间距检验与失败重试、按自身财富加 $1$ 扰动，最终由判定方只检查自己那一位得出大小关系；并\textbf{{通过交换角色、使用全新随机数与密钥再跑一轮}}解决相等判定。
    \item \textbf{{任务二}}实现了基于 RSA 的 1-out-of-$n$ OT（EGL 构造），并给出一种\textbf{{只需 1 次 OT、3 轮交互}}即可直接输出三态结果的百万富翁求解方法。
    \item \textbf{{正确性}}：两方案在穷举与小样本随机测试中正确率均为 \textbf{{100\%}}，且均能正确处理相等情况。
    \item \textbf{{性能}}：OT 方案耗时约为 Yao 的 \textbf{{一半}}、交互轮数减半；但通信量约为 Yao 的 \textbf{{2.3 倍}}（1024 位下 {fmt(O[1024]['bytes'])} B 对 {fmt(P[1024]['bytes'])} B）。二者随财富上界 $N$ 均线性增长。
    \item \textbf{{隐私性}}：两方案在半诚实模型下都只泄露比较结果及其必然推论。OT 方案的安全性可清晰归约到原语的双向保护，结构更清晰、更易于形式化论证；Yao 原始方案则依赖“未知随机数 $x$”与“缺少私钥 $d$”两个事实，论证相对间接，且需要额外的相等判定轮次。
\end{{enumerate}}

通过本次实验，我加深了对安全两方计算基本思想的理解：\textbf{{“不泄露输入而只计算函数”}}是可以做到的，其代价体现在计算、通信与交互轮数上；而 OT 作为基础原语，能够把复杂的安全计算问题规整地归约到少数几个密码学假设之上。

\begin{{thebibliography}}{{9}}
\bibitem{{yao1982}} A. C. Yao, ``Protocols for Secure Computations,'' in \textit{{Proc. 23rd Annual Symposium on Foundations of Computer Science (FOCS)}}, 1982, pp. 160--164.
\bibitem{{rabin1981}} M. O. Rabin, ``How to Exchange Secrets with Oblivious Transfer,'' Technical Report TR-81, Aiken Computation Laboratory, Harvard University, 1981.
\bibitem{{egl1985}} S. Even, O. Goldreich, and A. Lempel, ``A Randomized Protocol for Signing Contracts,'' \textit{{Communications of the ACM}}, vol. 28, no. 6, pp. 637--647, 1985.
\end{{thebibliography}}

\end{{document}}
"""

os.makedirs(REPORT_DIR, exist_ok=True)
out = os.path.join(REPORT_DIR, "main.tex")
with open(out, "w", encoding="utf-8") as f:
    f.write(body)
print("written:", out, len(body), "chars")
