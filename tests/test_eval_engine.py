#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评测引擎回归测试（unittest 独立测试目录）。

回归范围：每次改动后必须全绿的历史用例——
  1. 出题封印稳定：重复题号拒绝、题面/判据哈希入册；
  2. 确定性判分：exact / contains / numeric（含容差）；
  3. 语义题挂起不虚报（PENDING_SEMANTIC）；
  4. 分离纪律：裁判与被测同源拒判、未登记被测拒判；
  5. 台账防篡改：验链通过、改动现形（回归核心）；
  6. 报告根印稳定、台账只增不改。

运行：python3 -m unittest discover -s tests -t .   （仓库根目录下）
"""
import importlib.util
import json
import os
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "eval_engine_core", os.path.join(_REPO, "评测引擎.py"))
_core = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_core)
评测引擎 = _core.评测引擎
判分分离违规 = _core.判分分离违规
参赛未登记 = _core.参赛未登记


def _make_engine(judge="regression-judge", subject="subject-A"):
    eng = 评测引擎(judge, "v1", "回归测试")
    eng.登记被测对象(subject)
    return eng


class 封印回归(unittest.TestCase):
    def test_重复题号拒绝(self):
        eng = _make_engine()
        eng.出题("Q1", "1+1=?", {"type": "exact", "value": "2"})
        with self.assertRaises(ValueError):
            eng.出题("Q1", "1+1=?", {"type": "exact", "value": "2"})

    def test_封印哈希入册(self):
        eng = _make_engine()
        sealed = eng.出题("Q1", "题面", {"type": "exact", "value": "x"})
        self.assertTrue(sealed["题面哈希"])
        self.assertTrue(sealed["判据哈希"])
        self.assertEqual(sealed["判据类型"], "exact")

    def test_判据缺type拒绝(self):
        eng = _make_engine()
        with self.assertRaises(ValueError):
            eng.出题("Q1", "题面", {"value": "x"})


class 确定性判分回归(unittest.TestCase):
    def test_exact_命中与未命中(self):
        eng = _make_engine()
        eng.出题("E1", "1+1=?", {"type": "exact", "value": "2"})
        eng.提交作答("E1", " 2 ")
        self.assertEqual(eng.判分("E1")["verdict"], "PASS")
        eng.出题("E2", "1+1=?", {"type": "exact", "value": "2"})
        eng.提交作答("E2", "3")
        self.assertEqual(eng.判分("E2")["verdict"], "FAIL")

    def test_contains_判分(self):
        eng = _make_engine()
        eng.出题("C1", "列举哈希性质", {"type": "contains", "value": "抗篡改"})
        eng.提交作答("C1", "哈希链具备抗篡改能力")
        self.assertEqual(eng.判分("C1")["verdict"], "PASS")

    def test_numeric_容差判分(self):
        eng = _make_engine()
        eng.出题("N1", "圆周率约等于", {"type": "numeric", "value": 3.1416, "tolerance": 0.01})
        eng.提交作答("N1", "约 3.14")
        self.assertEqual(eng.判分("N1")["verdict"], "PASS")

    def test_未作答拒绝判分(self):
        eng = _make_engine()
        eng.出题("E1", "题", {"type": "exact", "value": "x"})
        with self.assertRaises(ValueError):
            eng.判分("E1")


class 分离纪律回归(unittest.TestCase):
    def test_未登记被测拒判(self):
        eng = 评测引擎("judge", "v1")  # 未登记被测
        eng.出题("E1", "题", {"type": "exact", "value": "x"})
        eng.提交作答("E1", "x")
        with self.assertRaises(参赛未登记):
            eng.判分("E1")

    def test_裁判被测同源拒判(self):
        eng = 评测引擎("same-identity", "v1")
        eng.登记被测对象("same-identity")
        eng.出题("E1", "题", {"type": "exact", "value": "x"})
        eng.提交作答("E1", "x")
        with self.assertRaises(判分分离违规):
            eng.判分("E1")

    def test_语义裁判同源拒判(self):
        eng = _make_engine(judge="judge-main", subject="spy-subject")
        eng.挂载语义判分器(
            lambda t, a, c: {"verdict": "PASS", "rationale": "r"},
            "spy-subject", "v1")
        eng.出题("S1", "开放题", {"type": "semantic"})
        eng.提交作答("S1", "作答")
        with self.assertRaises(判分分离违规):
            eng.判分("S1")


class 语义挂起回归(unittest.TestCase):
    def test_未挂裁判按挂起不虚报(self):
        eng = _make_engine()
        eng.出题("S1", "开放题", {"type": "semantic"})
        eng.提交作答("S1", "作答")
        r = eng.判分("S1")
        self.assertEqual(r["verdict"], "PENDING_SEMANTIC")
        self.assertIsNone(r["score"])

    def test_双模不一致记UNCERTAIN(self):
        eng = _make_engine()
        eng.挂载语义判分器(
            lambda t, a, c: {"verdict": "PASS", "rationale": "主"},
            "judge-1", "v1",
            cross_check={"callable": lambda t, a, c: {"verdict": "FAIL", "rationale": "副"},
                         "judge_id": "judge-2", "version": "v1"})
        eng.出题("S1", "开放题", {"type": "semantic"})
        eng.提交作答("S1", "作答")
        r = eng.判分("S1")
        self.assertEqual(r["verdict"], "UNCERTAIN")
        self.assertIsNone(r["score"])


class 台账防篡改回归(unittest.TestCase):
    def test_验链通过(self):
        eng = _make_engine()
        eng.出题("E1", "题", {"type": "exact", "value": "x"})
        eng.提交作答("E1", "x")
        eng.判分("E1")
        self.assertTrue(eng.verify_ledger())

    def test_篡改现形(self):
        eng = _make_engine()
        eng.出题("E1", "题", {"type": "exact", "value": "x"})
        eng.提交作答("E1", "x")
        eng.判分("E1")
        eng.ledger[1]["payload"]["题号"] = "被改题号"  # 模拟篡改
        self.assertFalse(eng.verify_ledger())

    def test_台账只增不改(self):
        eng = _make_engine()
        n0 = len(eng.ledger)
        eng.出题("E1", "题", {"type": "exact", "value": "x"})
        self.assertEqual(len(eng.ledger), n0 + 1)
        self.assertEqual(eng.ledger[0]["kind"], "ENGINE_INIT")

    def test_报告根印稳定(self):
        eng = _make_engine()
        eng.出题("E1", "题", {"type": "exact", "value": "x"})
        eng.提交作答("E1", "x")
        eng.判分("E1")
        root1 = eng.报告根印()
        root2 = eng.报告根印()
        self.assertEqual(root1, root2)
        report = eng.报告摘要()
        self.assertTrue(report["ledger_verified"])
        self.assertEqual(report["rows"][0]["题号"], "E1")


if __name__ == "__main__":
    unittest.main()
