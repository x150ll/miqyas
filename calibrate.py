#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIQYAS — calibration inspector (OPTIONAL)

The site now calibrates itself automatically: every browser reads the shared
anonymous aggregate and fits real item parameters on the fly. Nothing to run,
nothing to upload. This tool only lets YOU look at what the crowd has taught it.

  python calibrate.py https://miqyas-b8972-default-rtdb.firebaseio.com
  python calibrate.py <db-url> --write    # also emit params.json (manual override — pins recipes)
  python calibrate.py --selftest

No secret needed: the aggregate is public, anonymous counters.
"""
import sys, json, math, urllib.request

BINS, LO, W = 13, -3.25, 0.5
D, PEN_A = 1.7, 8.0
C_BY = {"pat": 1/8, "num": 0.02, "spa": 0.2, "mem": 0.02}
NB = {"add": -1.65, "alt": -0.55, "mult": -0.2, "quad": 0.45, "fib": 0.7,
      "inter": 0.95, "multadd": 1.15, "pow": 1.4, "altmult": 1.65, "cube": 1.95}
PW = {"c": 0.15, "p": 0.55, "d": 0.85, "a": 1.05, "x": 1.2}

clamp = lambda v, a, b: min(b, max(a, v))
bin_th = lambda i: LO + W * (i + 0.5)

def pred_b(sig):
    dom, _, rest = sig.partition("_")
    if dom == "pat":
        if rest.startswith("ana-"):
            W2 = {"z": 0.35, "r": 0.5, "f": 0.45, "n": 0.55, "t": 0.4}
            ls = list(rest[4:])
            return clamp(-1.5 + 0.4 * (len(ls) - 1) + sum(W2.get(l, 0.45) for l in ls), -1.3, 1.9)
        toks = [t for t in rest.split("-") if t]
        b = -1.9 + 0.32 * (len(toks) - 1) + sum(PW.get(t[0], 0.6) for t in toks)
        if any(t[0] == "x" for t in toks) and any(t[0] == "a" for t in toks):
            b += 0.15
        return clamp(b, -2.4, 3.0)
    if dom == "num": return NB.get(rest, 0.0)
    if dom == "spa":
        if rest.startswith("f") and len(rest) >= 3:
            K, P = int(rest[1]), int(rest[2])
            return clamp(-1.35 + 0.9 * (K - 1) + 0.35 * (P - 1), -1.5, 1.6)
        return clamp(-1.05 + 0.3 * ((int(rest) if rest.isdigit() else 6) - 5), -1.5, 2.25)
    if dom == "mem":
        if rest.startswith("b"):
            L = int(rest[1:]) if rest[1:].isdigit() else 4
            return clamp(-1.1 + 0.55 * (L - 3), -1.35, 2.05)
        return clamp(-1.7 + 0.55 * ((int(rest) if rest.isdigit() else 4) - 3), -1.9, 1.85)
    return 0.0

def p3(t, a, b, c): return c + (1 - c) / (1 + math.exp(-D * a * (t - b)))

def fit_binned(N, C, c):
    def obj(a, b):
        s = PEN_A * (a - 1) ** 2
        for i in range(BINS):
            n = N[i]
            if not n: continue
            k = min(C[i], n)
            p = clamp(p3(bin_th(i), a, b, c), 1e-6, 1 - 1e-6)
            s -= k * math.log(p) + (n - k) * math.log(1 - p)
        return s
    best = (1.0, 0.0, float("inf"))
    a = 0.5
    while a <= 2.005:
        b = -2.8
        while b <= 3.205:
            v = obj(a, b)
            if v < best[2]: best = (a, b, v)
            b += 0.1
        a += 0.1
    a, b, _ = best
    step = 0.05
    while step > 0.004:
        moved = True
        while moved:
            moved = False
            for da, db in ((step,0),(-step,0),(0,step),(0,-step),
                           (step,step),(step,-step),(-step,step),(-step,-step)):
                na, nb = a + da, b + db
                if not (0.3 <= na <= 2.4 and -3.2 <= nb <= 3.6): continue
                v = obj(na, nb)
                if v < best[2] - 1e-9:
                    a, b, best = na, nb, (na, nb, v); moved = True
        step /= 2
    return a, b

def read_rec(rec):
    N, C = [], []
    for i in range(BINS):
        n = min(max(int(rec.get(f"n{i}", 0) or 0), 0), 4000)
        k = min(max(int(rec.get(f"c{i}", 0) or 0), 0), n)
        N.append(n); C.append(k)
    return N, C

def effective(sig, N, C):
    """Same shrinkage + trust region the site applies in every browser."""
    tot = sum(N); cov = sum(1 for n in N if n >= 8)
    if tot < 100 or cov < 4: return None
    c = C_BY.get(sig.split("_", 1)[0], 0.02)
    fa, fb = fit_binned(N, C, c)
    pb = pred_b(sig)
    w = tot / (tot + 150)
    b = clamp(pb + (fb - pb) * w, pb - 1.5, pb + 1.5)
    a = clamp(1 + (fa - 1) * w, 0.6, 1.8)
    return {"a": round(a, 3), "b": round(b, 3), "n": tot, "raw_a": fa, "raw_b": fb, "pred": pb}

def selftest():
    ok = True
    print("— parameter recovery on synthetic bins —")
    for ta, tb, c in [(1.1, -0.8, 1/8), (1.2, 1.4, 0.02), (0.95, 0.3, 0.2)]:
        N = [120] * BINS
        C = [round(120 * p3(bin_th(i), ta, tb, c)) for i in range(BINS)]
        fa, fb = fit_binned(N, C, c)
        print(f"  true a={ta} b={tb:+.2f} → fit a={fa:.2f} b={fb:+.2f}")
        ok &= abs(fb - tb) < 0.10 and abs(fa - ta) < 0.30
    print("— trust region caps deliberate poisoning —")
    sig = "spa_6"; pb = pred_b(sig)          # -0.75
    tb = pb + 3.0                            # attacker pushes difficulty +3 logits
    N = [900] * BINS                          # flooded counters
    C = [round(900 * p3(bin_th(i), 1.0, tb, 0.2)) for i in range(BINS)]
    eff = effective(sig, N, C)
    print(f"  attacker target b={tb:+.2f} → effective b={eff['b']:+.2f} (bound {pb+1.5:+.2f})")
    ok &= eff["b"] <= pb + 1.5 + 1e-9
    print("SELFTEST:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)

def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest": selftest()
    if len(sys.argv) < 2: print(__doc__); sys.exit(1)
    base = sys.argv[1].rstrip("/")
    write = "--write" in sys.argv
    with urllib.request.urlopen(f"{base}/agg.json", timeout=60) as r:
        agg = json.load(r) or {}
    out, popN = {}, [0] * BINS
    w = max([len(k) for k in agg] + [10])
    print(f"{'recipe'.ljust(w)}  {'n':>6}  {'pred b':>7}  {'real b':>7}  {'shift':>6}  {'a':>5}  note")
    for sig in sorted(agg):
        rec = agg[sig]
        if not isinstance(rec, dict): continue
        N, C = read_rec(rec)
        for i in range(BINS): popN[i] += N[i]
        eff = effective(sig, N, C)
        if not eff:
            print(f"{sig.ljust(w)}  {sum(N):>6}  {pred_b(sig):>+7.2f}  {'—':>7}  {'—':>6}  {'—':>5}  collecting…")
            continue
        note = "LOW DISCRIMINATION — consider retiring" if eff["raw_a"] < 0.55 else ""
        rts, rtn = int(rec.get("rts", 0) or 0), int(rec.get("rtn", 0) or 0)
        mrt = f"{rts/rtn/1000:4.1f}s" if rtn >= 20 else "  — "
        print(f"{sig.ljust(w)}  {eff['n']:>6}  {eff['pred']:>+7.2f}  {eff['b']:>+7.2f}  {eff['b']-eff['pred']:>+6.2f}  {eff['a']:>5.2f}  rt̄={mrt}  {note}")
        out[sig] = {"a": eff["a"], "b": eff["b"], "n": eff["n"]}
    tot = sum(popN)
    if tot >= 300:
        m = sum(popN[i] * bin_th(i) for i in range(BINS)) / tot
        sd = math.sqrt(sum(popN[i] * (bin_th(i) - m) ** 2 for i in range(BINS)) / tot)
        print(f"\naudience (n={tot}): mean θ={m:+.2f} sd={sd:.2f} → averages ≈ IQ {100+15*m:.0f} on this scale")
    if write:
        with open("params.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"\nWrote params.json ({len(out)} recipes) — note: uploading it PINS these recipes (manual wins over auto).")

if __name__ == "__main__":
    main()
