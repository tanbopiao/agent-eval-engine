#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评测引擎 MCP 服务壳

把可验证评测引擎（确定性判分优先、哈希链台账、判分与被测分离）以 MCP 工具
形式对外暴露。引擎本体零依赖纯标准库；本壳仅依赖 mcp 包。

启动配置（stdio）：
    {
      "mcpServers": {
        "agent-eval-engine": {
          "command": "python3",
          "args": ["/path/to/agent-eval-engine/mcp_server.py"]
        }
      }
    }

工具一览（先 new_engine 建场，再按 登记被测 → 出题 → 作答 → 判分 → 报告 推进）：
    new_engine       建场：登记判分模型身份（分离纪律：裁判必须显式在册）
    register_subject 参赛登记：登记被测对象，未登记拒判
    seal_question    出题封印：题面/判据哈希入册，重复题号拒绝
    submit_answer    受控作答：答案哈希入账
    score_question   级联判分：确定性优先，语义挂起不虚报，同源即拒
    report_summary   报告摘要：逐题结论 + 验链 + 报告根印
    verify_ledger    台账验链：哈希链逐条重算，篡改现形
"""
import json
import os
import sys

from mcp.server.fastmcp import FastMCP

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import importlib.util                              # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "eval_engine_core", os.path.join(_HERE, "评测引擎.py"))
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)
评测引擎 = _core.评测引擎

mcp = FastMCP("agent-eval-engine")

_engine = None


def _need_engine():
    if _engine is None:
        raise RuntimeError("尚未建场：请先调用 new_engine 登记判分模型")
    return _engine


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False)


@mcp.tool()
def new_engine(judge_name: str, judge_version: str, judge_note: str = "") -> str:
    """建场：创建评测引擎实例并登记判分模型身份（名称+版本必填，分离纪律硬约束）。"""
    global _engine
    _engine = 评测引擎(judge_name, judge_version, judge_note)
    return _dump({"ok": True, "judge": _engine.judge["name"] + "@" + _engine.judge["version"]})


@mcp.tool()
def register_subject(subject_id: str) -> str:
    """参赛登记：登记被测对象标识。与判分模型同源时判分入口会拒绝执行。"""
    eng = _need_engine()
    eng.登记被测对象(subject_id)
    return _dump({"ok": True, "subject": subject_id})


@mcp.tool()
def seal_question(qid: str, question: str, criteria: dict) -> str:
    """出题封印：题面与判据哈希入册。criteria 示例：
    {"type": "exact", "value": "42"}；type 可选 exact/contains/not_contains/regex/numeric/semantic。"""
    eng = _need_engine()
    sealed = eng.出题(qid, question, criteria)
    return _dump({"ok": True, "题号": qid, "题面哈希": sealed["题面哈希"], "判据类型": sealed["判据类型"]})


@mcp.tool()
def submit_answer(qid: str, answer: str, metadata: dict = None) -> str:
    """受控作答：提交某题答案，答案哈希入账。"""
    eng = _need_engine()
    h = eng.提交作答(qid, answer, metadata)
    return _dump({"ok": True, "题号": qid, "答案哈希": h})


@mcp.tool()
def score_question(qid: str) -> str:
    """级联判分：确定性规则优先；语义题未挂裁判按 PENDING_SEMANTIC 挂起，不猜测分数。"""
    eng = _need_engine()
    return _dump(eng.判分(qid))


@mcp.tool()
def report_summary() -> str:
    """报告摘要：逐题结论、台账验链状态与报告根印（可对印复算）。"""
    eng = _need_engine()
    return _dump(eng.报告摘要())


@mcp.tool()
def verify_ledger() -> str:
    """台账验链：逐条重算哈希链，任何篡改当场现形。"""
    eng = _need_engine()
    return _dump({"ledger_verified": eng.verify_ledger(), "entries": len(eng.ledger)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
