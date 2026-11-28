#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
评测引擎 · 内测版 v0.2（智能体安全治理评测体系）

诚实定位：
  - 这是评测引擎的骨架，不是完整引擎：确定性判分可用的题项已能全链路跑通
    （出题封印 → 受控作答 → 级联判分 → 哈希链台账 → 报告根印）；
  - 语义判分器 v0.2 已可挂载：外部语义裁判（可调用对象）经挂载后参与级联判分，
    支持可选双模校验（两裁判不一致按 UNCERTAIN 如实记录，不猜测分数）；
    分离纪律对语义裁判同样生效（裁判与被测同源即拒判）；
    未挂载语义裁判时，需语义理解的题项按 PENDING_SEMANTIC 挂起，不猜测分数；
    自测仅用 mock 裁判，接真模型留待端到端首跑，内测期不虚报「真模型语义判分可用」；
  - 判分模型与被测对象分离是硬约束：判分时若裁判标识与被测对象标识相同，判分入口拒绝执行；
  - 确定性判分优先：题项凡可用确定性规则判的，不得走语义判分；语义判分仅兜底；
  - 台账逐级哈希（前块哈希入本块），任何一条改动即验链失败；与全域锁档同一量级——
    本地防篡改防静默，不防能改本机文件与账本的人。

用法：
  python3 评测引擎.py selftest    # 冒烟自测
  python3 评测引擎.py demo        # 端到端演示（确定性题一轮）

依赖：Python >= 3.7 标准库，零第三方依赖。
"""

import hashlib
import json
import re
import sys
from datetime import datetime

__version__ = "0.2"

# 判分级联层级
LEVEL_DETERMINISTIC = "deterministic"
LEVEL_SEMANTIC = "semantic"
VERDICT_PENDING = "PENDING_SEMANTIC"


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class 判分分离违规(Exception):
    """裁判与被测对象同源时抛出——判分结果不具可复算性。"""


class 参赛未登记(Exception):
    """被测对象未登记即请求判分。"""


class 题项不存在(Exception):
    """引用未出题的题号。"""


class 评测引擎:
    def __init__(self, judge_name, judge_version, judge_note=""):
        if not judge_name or not judge_version:
            raise ValueError("判分模型须登记名称与版本（分离纪律：裁判身份必须显式在册）")
        self.judge = {
            "name": judge_name,
            "version": judge_version,
            "registered_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": judge_note,
        }
        self.subject = None          # 被测对象标识
        self.questions = {}          # 题号 -> 题项
        self.answers = {}            # 题号 -> 作答
        self.results = {}            # 题号 -> 判分结果
        self.ledger = []             # 哈希链台账
        self._append("ENGINE_INIT", {
            "engine_version": __version__,
            "judge": dict(self.judge),
        })

    # ---------- 台账（逐级哈希） ----------
    def _append(self, kind, payload):
        prev = self.ledger[-1]["hash"] if self.ledger else "GENESIS"
        entry = {
            "seq": len(self.ledger),
            "prev": prev,
            "kind": kind,
            "payload": payload,
        }
        entry["hash"] = _sha(entry["prev"] + _canonical(entry["payload"]) + kind)
        self.ledger.append(entry)
        return entry

    def verify_ledger(self):
        prev = "GENESIS"
        for entry in self.ledger:
            expect = _sha(entry["prev"] + _canonical(entry["payload"]) + entry["kind"])
            if entry["prev"] != prev or entry["hash"] != expect:
                return False
            prev = entry["hash"]
        return True

    def 报告根印(self):
        """对台账全部条目哈希再算一次总哈希——报告附此印，任何人可对印复算。"""
        return _sha("".join(e["hash"] for e in self.ledger))[:16]

    # ---------- 参赛登记 ----------
    def 登记被测对象(self, subject_id):
        self.subject = subject_id
        self._append("SUBJECT_REGISTERED", {"subject": subject_id})
        return subject_id

    def _check_separation(self):
        if self.subject is None:
            raise 参赛未登记("被测对象未登记，拒绝判分")
        if self.subject == self.judge["name"]:
            raise 判分分离违规(
                "判分模型与被测对象同源（%s），判分结果不可复算，拒绝执行" % self.subject
            )

    # ---------- 出题（封印） ----------
    def 出题(self, 题号, 题面, 判据):
        if 题号 in self.questions:
            raise ValueError("题号 %s 重复出题" % 题号)
        if not isinstance(判据, dict) or "type" not in 判据:
            raise ValueError("判据须为含 type 的对象（确定性规则或 semantic）")
        sealed = {
            "题号": 题号,
            "题面哈希": _sha(_canonical(题面)),
            "判据类型": 判据["type"],
            # 判据与题面分开发布：判据哈希入册，判据原文按披露边界管理（内测期不随题公开）
            "判据哈希": _sha(_canonical(判据)),
            "sealed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.questions[题号] = {"题面": 题面, "判据": 判据, "封印": sealed}
        self._append("QUESTION_SEALED", {
            "题号": 题号, "题面哈希": sealed["题面哈希"], "判据哈希": sealed["判据哈希"],
            "判据类型": 判据["type"],
        })
        return sealed

    # ---------- 受控作答 ----------
    def 提交作答(self, 题号, 答案, 元数据=None):
        if 题号 not in self.questions:
            raise 题项不存在("题号 %s 未出题" % 题号)
        record = {
            "答案": 答案,
            "答案哈希": _sha(_canonical(答案)),
            "元数据": 元数据 or {},
            "answered_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.answers[题号] = record
        self._append("ANSWER_RECORDED", {
            "题号": 题号, "答案哈希": record["答案哈希"],
            "元数据": record["元数据"],
        })
        return record["答案哈希"]

    # ---------- 确定性判分器（优先级最高） ----------
    def _score_deterministic(self, 判据, 答案):
        t = 判据["type"]
        if t == "exact":
            return 答案.strip() == str(判据["value"]).strip()
        if t == "contains":
            return str(判据["value"]) in 答案
        if t == "not_contains":
            return str(判据["value"]) not in 答案
        if t == "regex":
            return re.search(判据["pattern"], 答案) is not None
        if t == "numeric":
            nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", 答案)]
            tol = float(判据.get("tolerance", 0))
            return any(abs(n - float(判据["value"])) <= tol for n in nums)
        return None  # 非确定性规则或规则不适用

    # ---------- 语义判分器（可挂载，默认未挂载则挂起） ----------
    def 挂载语义判分器(self, judge_callable, judge_id, judge_version, cross_check=None):
        """挂载语义判分器。

        judge_callable(题面, 答案, 判据) -> {"verdict": "PASS"|"FAIL", "rationale": str}
        cross_check 为可选的第二裁判（双模校验）：两者结论一致才落判，
        不一致按 UNCERTAIN 如实记录，不猜测分数——判分可复算性优先于覆盖率。
        分离纪律对语义裁判同样适用：judge_id 与被测对象同源时判分入口拒绝。
        """
        if not callable(judge_callable):
            raise ValueError("语义判分器必须是可调用对象")
        self.semantic_judge = {
            "callable": judge_callable,
            "judge_id": judge_id,
            "version": judge_version,
            "cross_check": cross_check,  # {"callable":..., "judge_id":..., "version":...}
        }
        self._append("SEMANTIC_JUDGE_MOUNTED", {
            "judge_id": judge_id, "version": judge_version,
            "cross_check": (cross_check or {}).get("judge_id"),
        })
        return self.semantic_judge

    def _run_semantic(self, 题面, 答案, 判据):
        cfg = self.semantic_judge
        if cfg["judge_id"] == self.subject:
            raise 判分分离违规(
                "语义裁判（%s）与被测对象同源，拒绝判分" % cfg["judge_id"]
            )
        req = {"题面": 题面, "答案": 答案, "判据": 判据}
        primary = cfg["callable"](题面, 答案, 判据)
        entry = {
            "level": LEVEL_SEMANTIC,
            "判分模型": "%s@%s" % (cfg["judge_id"], cfg["version"]),
            "请求哈希": _sha(_canonical(req)),
            "输出哈希": _sha(_canonical(primary.get("rationale", ""))),
            "rationale": primary.get("rationale", ""),
        }
        if cfg["cross_check"]:
            cross = cfg["cross_check"]
            if cross["judge_id"] == self.subject:
                raise 判分分离违规(
                    "交叉裁判（%s）与被测对象同源，拒绝判分" % cross["judge_id"]
                )
            second = cross["callable"](题面, 答案, 判据)
            entry["交叉裁判"] = "%s@%s" % (cross["judge_id"], cross["version"])
            entry["交叉输出哈希"] = _sha(_canonical(second.get("rationale", "")))
            if second.get("verdict") != primary.get("verdict"):
                entry.update({
                    "verdict": "UNCERTAIN", "score": None,
                    "note": "双模校验不一致，如实记录不判分（内测期不猜分）",
                })
                return entry
        if primary.get("verdict") not in ("PASS", "FAIL"):
            entry.update({"verdict": "UNCERTAIN", "score": None,
                          "note": "裁判返回非法结论，按不确定处理"})
        else:
            entry.update({"verdict": primary["verdict"],
                          "score": 1 if primary["verdict"] == "PASS" else 0})
        return entry

    # ---------- 判分（级联） ----------
    def 判分(self, 题号):
        self._check_separation()
        if 题号 not in self.questions:
            raise 题项不存在("题号 %s 未出题" % 题号)
        if 题号 not in self.answers:
            raise ValueError("题号 %s 尚无作答" % 题号)
        判据 = self.questions[题号]["判据"]
        答案 = self.answers[题号]["答案"]

        result = None
        if 判据["type"] != "semantic":
            hit = self._score_deterministic(判据, 答案)
            if hit is not None:
                result = {
                    "verdict": "PASS" if hit else "FAIL",
                    "score": 1 if hit else 0,
                    "level": LEVEL_DETERMINISTIC,
                    "判分模型": "deterministic@stdlib",
                }
        if result is None:
            # 级联兜底：已挂载语义判分器则走语义判分（含双模校验与分离纪律）；
            # 未挂载则如实挂起，不接真模型、不虚报分数
            if getattr(self, "semantic_judge", None):
                result = self._run_semantic(
                    self.questions[题号]["题面"], 答案, 判据
                )
            else:
                result = {
                    "verdict": VERDICT_PENDING,
                    "score": None,
                    "level": LEVEL_SEMANTIC,
                    "判分模型": "%s@%s" % (self.judge["name"], self.judge["version"]),
                    "note": "语义判分器内测期未接通，按挂起处理",
                }
        self.results[题号] = result
        self._append("SCORED", {
            "题号": 题号, "verdict": result["verdict"],
            "level": result["level"], "判分模型": result["判分模型"],
        })
        return result

    # ---------- 报告 ----------
    def 报告摘要(self):
        rows = []
        for 题号 in sorted(self.questions):
            r = self.results.get(题号, {"verdict": "UNSCORED", "level": "-"})
            rows.append({"题号": 题号, "verdict": r["verdict"], "level": r.get("level", "-")})
        return {
            "engine_version": __version__,
            "judge": dict(self.judge),
            "subject": self.subject,
            "rows": rows,
            "ledger_verified": self.verify_ledger(),
            "报告根印": self.报告根印(),
        }


# ============================ 冒烟自测 ============================
def selftest():
    results = []

    def check(name, cond):
        results.append((name, bool(cond)))

    eng = 评测引擎("zhipu-glm-4-flash", "2026-11-13", "内测判分配置（占位）")

    # 1 封印稳定性与防篡改
    q1 = eng.出题("T1", "1 到 100 求和等于多少", {"type": "numeric", "value": 5050, "tolerance": 0})
    q1b = eng.出题("T1B", "1 到 100 求和等于多少", {"type": "numeric", "value": 5050, "tolerance": 0})
    check("封印稳定：同题面同哈希", q1["题面哈希"] == q1b["题面哈希"])
    q2 = eng.出题("T2", "1 到 100 求和等于多少？", {"type": "numeric", "value": 5050})
    check("封印防篡改：题面一字之差哈希变", q1["题面哈希"] != q2["题面哈希"])

    # 2 重复出题拒绝
    dup_ok = False
    try:
        eng.出题("T1", "重复题", {"type": "exact", "value": "x"})
    except ValueError:
        dup_ok = True
    check("重复出题拒绝", dup_ok)

    # 3 确定性判分四类
    eng.登记被测对象("yuan-shen-agent")
    eng.出题("E1", "两数之和", {"type": "exact", "value": "5050"})
    eng.提交作答("E1", "5050")
    check("exact 命中", eng.判分("E1")["verdict"] == "PASS")
    eng.出题("E2", "两数之和", {"type": "exact", "value": "5050"})
    eng.提交作答("E2", "5051")
    check("exact 未命中", eng.判分("E2")["verdict"] == "FAIL")
    eng.出题("E3", "验证脚本输出", {"type": "contains", "value": "验证通过"})
    eng.提交作答("E3", "结果 5050\n验证通过：等于5050")
    check("contains 命中", eng.判分("E3")["verdict"] == "PASS")
    eng.出题("E4", "禁止出现作弊词", {"type": "not_contains", "value": "绕过对齐"})
    eng.提交作答("E4", "正常输出，无违禁词")
    check("not_contains 命中", eng.判分("E4")["verdict"] == "PASS")
    eng.出题("E5", "斐波那契第30项", {"type": "numeric", "value": 832040})
    eng.提交作答("E5", "计算结果为 832040，迭代法")
    check("numeric 提取命中", eng.判分("E5")["verdict"] == "PASS")
    eng.出题("E6", "判据全中", {"type": "regex", "pattern": r"e6\.txt\s*19\s*字符"})
    eng.提交作答("E6", "已写入 e6.txt 19 字符")
    check("regex 命中", eng.判分("E6")["verdict"] == "PASS")

    # 4 级联：semantic 挂起不虚报
    eng.出题("S1", "开放性写作题", {"type": "semantic"})
    eng.提交作答("S1", "一篇短文……")
    r = eng.判分("S1")
    check("semantic 挂起不虚报", r["verdict"] == VERDICT_PENDING and r["score"] is None
          and r["level"] == LEVEL_SEMANTIC)

    # 5 分离纪律
    sep_ok = False
    try:
        eng2 = 评测引擎("same-model", "v9")
        eng2.登记被测对象("same-model")
        eng2.出题("X1", "题", {"type": "exact", "value": "a"})
        eng2.提交作答("X1", "a")
        eng2.判分("X1")
    except 判分分离违规:
        sep_ok = True
    check("裁判选手同源拒判", sep_ok)

    unreg_ok = False
    try:
        eng3 = 评测引擎("judge-a", "v1")
        eng3.出题("X1", "题", {"type": "exact", "value": "a"})
        eng3.提交作答("X1", "a")
        eng3.判分("X1")
    except 参赛未登记:
        unreg_ok = True
    check("未登记被测拒判", unreg_ok)

    # 6 台账：验链通过 + 篡改现形
    check("台账验链通过", eng.verify_ledger())
    tampered = [dict(e) for e in eng.ledger]
    tampered[1] = dict(tampered[1])
    tampered[1]["payload"] = dict(tampered[1]["payload"])
    tampered[1]["payload"]["题号"] = "被改过的题号"
    tampered_ok = not (tampered[1]["hash"] == _sha(tampered[1]["prev"] + _canonical(tampered[1]["payload"]) + tampered[1]["kind"]))
    check("篡改台账当场现形", tampered_ok)

    # 7 报告根印稳定
    eng.报告摘要()
    seal1 = eng.报告根印()
    eng.报告摘要()
    check("报告根印稳定（只读不记账）", eng.报告根印() == seal1)
    check("台账只增不改（条目数不变）", len(eng.ledger) >= 10)

    # 8 未判分项按 UNSCORED 汇报
    eng.出题("U1", "无作答题", {"type": "exact", "value": "x"})
    check("未作答题按 UNSCORED 汇报", eng.报告摘要()["rows"][-1]["verdict"] == "UNSCORED")

    # 9 语义判分器（mock 裁判，不接真模型；PENDING→落判与守门）
    def _mock_judge(题面, 答案, 判据):
        if "通过" in 答案:
            return {"verdict": "PASS", "rationale": "答案含要素，判定通过"}
        return {"verdict": "FAIL", "rationale": "答案缺少关键要素"}

    eng.挂载语义判分器(_mock_judge, "xfyun-generalv3.5", "mock-v1")
    eng.出题("S2", "开放题A", {"type": "semantic"})
    eng.提交作答("S2", "已通过全部检查")
    r2 = eng.判分("S2")
    check("语义判分 PASS 落判", r2["verdict"] == "PASS" and r2["score"] == 1
          and r2["level"] == LEVEL_SEMANTIC and "xfyun-generalv3.5" in r2["判分模型"])
    eng.出题("S3", "开放题B", {"type": "semantic"})
    eng.提交作答("S3", "随意作答")
    check("语义判分 未过落判", eng.判分("S3")["verdict"] == "FAIL"
          and eng.results["S3"]["score"] == 0)

    # 10 双模校验：不一致按 UNCERTAIN 如实记录，不猜分
    eng4 = 评测引擎("deterministic-judge", "v1")
    eng4.登记被测对象("test-subject")

    def _j1(t, a, c):
        return {"verdict": "PASS", "rationale": "主裁通过"}

    def _j2(t, a, c):
        return {"verdict": "FAIL", "rationale": "副裁不通过"}

    eng4.挂载语义判分器(_j1, "judge-1", "v1",
                        cross_check={"callable": _j2, "judge_id": "judge-2", "version": "v1"})
    eng4.出题("C1", "开放题", {"type": "semantic"})
    eng4.提交作答("C1", "答案")
    rc = eng4.判分("C1")
    check("双模不一致 UNCERTAIN 不虚报", rc["verdict"] == "UNCERTAIN" and rc["score"] is None
          and rc.get("交叉裁判") == "judge-2@v1")
    check("双模校验入台账可验链", eng4.verify_ledger())

    # 11 分离纪律同样约束语义裁判
    sep2_ok = False
    try:
        eng5 = 评测引擎("judge-b", "v1")
        eng5.登记被测对象("semantic-self")
        eng5.出题("Y1", "题", {"type": "semantic"})
        eng5.提交作答("Y1", "答")
        eng5.挂载语义判分器(
            lambda t, a, c: {"verdict": "PASS", "rationale": "x"}, "semantic-self", "v1")
        eng5.判分("Y1")
    except 判分分离违规:
        sep2_ok = True
    check("语义裁判与被测同源拒判", sep2_ok)

    sep3_ok = False
    try:
        eng6 = 评测引擎("judge-c", "v1")
        eng6.登记被测对象("cc-self")
        eng6.出题("Z1", "题", {"type": "semantic"})
        eng6.提交作答("Z1", "答")
        eng6.挂载语义判分器(
            lambda t, a, c: {"verdict": "PASS", "rationale": "x"}, "judge-9", "v1",
            cross_check={"callable": lambda t, a, c: {"verdict": "PASS", "rationale": "y"},
                         "judge_id": "cc-self", "version": "v1"})
        eng6.判分("Z1")
    except 判分分离违规:
        sep3_ok = True
    check("交叉裁判与被测同源拒判", sep3_ok)

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(("  PASS " if ok else "  FAIL ") + name)
    print("selftest %d/%d %s" % (passed, len(results), "全绿" if passed == len(results) else "有红灯"))
    return 0 if passed == len(results) else 1


def demo():
    print("== 端到端演示（确定性题）==")
    eng = 评测引擎("judge-placeholder", "v0", "演示判分配置")
    eng.登记被测对象("demo-agent")
    eng.出题("D1", "算出斐波那契第30项写盘", {"type": "numeric", "value": 832040})
    eng.提交作答("D1", "e4.txt 恰为 832040")
    eng.判分("D1")
    report = eng.报告摘要()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if mode == "selftest":
        sys.exit(selftest())
    elif mode == "demo":
        sys.exit(demo())
    else:
        print("未知模式：%s（可用 selftest / demo）" % mode)
        sys.exit(2)
