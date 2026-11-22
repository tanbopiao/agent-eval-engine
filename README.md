# 评测引擎 · Verifiable Eval Engine（骨架版）

> 给智能体评测装上「可验证」底座的单文件引擎：**确定性判分优先、哈希链台账、判分与被测分离**。
> 纯 Python 标准库，零第三方依赖，单文件即用。

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/)

## 诚实定位

这是评测引擎的**骨架**，不是完整引擎：

- 确定性判分可用的题项已能全链路跑通：**出题封印 → 受控作答 → 级联判分 → 哈希链台账 → 报告根印**；
- 语义判分器以**可挂载外部裁判**的方式接入：支持双模校验（两裁判不一致按 UNCERTAIN 如实记录，不猜测分数）；
- **分离纪律是硬约束**：裁判与被测同源即拒判；未登记的被测对象拒判；
- 未挂载语义裁判时，需语义理解的题项按 PENDING_SEMANTIC 挂起——**不虚报、不猜测分数**；
- 本地哈希链防篡改防静默，不防能改本机文件与账本的人。

## 设计原则

1. **确定性判分优先**：凡可用确定性规则判的题项，不走语义判分；语义判分仅兜底；
2. **台账逐级哈希**：前块哈希入本块，任何一条改动即验链失败；
3. **报告根印**：报告内容哈希锚定，只读不记账；
4. **分离纪律**：判分模型与被测对象分离，同源即拒。

## 快速开始

```bash
python3 评测引擎.py selftest   # 23 项冒烟自测
python3 评测引擎.py demo       # 端到端演示（确定性题一轮）
```

依赖：Python >= 3.7 标准库，零第三方依赖。

## 自测覆盖（23/23 全绿）

封印稳定与防篡改、重复出题拒绝、exact/contains/not_contains/numeric/regex 判分、
语义题挂起不虚报、裁判选手同源拒判、未登记被测拒判、台账验链、篡改现形、
报告根印稳定、台账只增不改、双模不一致 UNCERTAIN、双模校验入账可验链等。

## 适用场景

- 智能体能力与安全评测的**可验证判分底座**；
- 需要判分过程**可审计、可复算**的评测流程；
- 作为更完整评测体系（语义裁判、题库管理、报告平台）的内核骨架。

## 相关项目

- [constraint-runtime](https://github.com/tanbopiao/constraint-runtime) — 智能体约束运行时组件集（围栏规则引擎、影子运行器、熔断停机器、留痕重放器）
- [sop-retrieval-mcp](https://github.com/tanbopiao/sop-retrieval-mcp) — SOP 检索 MCP 本地评估包（答案带出处）

## License

Apache 2.0 — see [LICENSE](LICENSE).
