# 命理验证数据库

本目录已经落地为 SQLite 数据库，服务于三件事：

1. 保存理论规则与来源证据。
2. 保存本地案例、纠偏记录和报告质检。
3. 承接未来 1000万人公开样本验证工程。

## 文件

- `database/schema.sql`：正式表结构。
- `scripts/init_database.py`：初始化数据库并导入种子数据。
- `scripts/import_wikidata_seed.py`：从 Wikidata 导入公开人物种子样本。
- `scripts/import_wikidata_entities.py`：通过 Wikidata API 按 QID 导入公开人物实体、职业、国家、死亡事件。
- `scripts/import_wikipedia_birth_year.py`：从 Wikipedia 出生年份分类扩展公开人物 QID，再导入 Wikidata 实体。
- `scripts/import_wikipedia_year_range.py`：按出生年份范围限速扩展样本，失败记录到导入批次表。
- `scripts/import_wikipedia_year_range_bulk.py`：并发查询出生年份、分块顺序入库，并支持断点续跑和 Wikidata 日期索引模式。
- `scripts/audit_year_coverage.py`：审计指定年份范围的连续覆盖、缺失年份和每年记录量。
- `scripts/calculate_chart_snapshots.py`：根据出生事实生成三柱或四柱命盘快照，并保存十神、藏干、五行、纳音、合冲和边界标记。
- `scripts/build_precision_foundation.py`：生成严格资料等级、报告准入范围及固定训练/验证/测试划分。
- `scripts/enrich_wikidata_life_events.py`：补充具有明确日期限定的公开人生事件。
- `scripts/enrich_wikidata_birthplaces.py`：按公开出生地 QID 回填坐标和时区实体引用。
- `scripts/evaluate_quality_rules.py`：生成安全规则检查、偏差矩阵和验证资格指标。
- `scripts/report_gate.py`：报告生成前检查资料是否支持所请求的分析模块。
- `scripts/rebuild_database.py`：一键重建数据库，串起初始化、导入、快照、评估和校验。
- `scripts/db_stats.py`：输出数据库统计。
- `scripts/validate_database.py`：校验表结构、JSON 字段和外键。
- `data/mingli_validation.db`：本地 SQLite 数据库，由初始化脚本生成。

## 初始化

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\init_database.py --reset
```

## 一键重建

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\rebuild_database.py
```

如果当前网络无法访问 Wikidata，可先跳过公开人物导入：

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\rebuild_database.py --skip-wikidata
```

## 当前已入库内容

- 来源登记：公开数据源、私有反馈源、参考资料源。
- 理论规则：月令优先、无时辰降级、真太阳时边界、闰月确认、案例回验、健康边界、财务边界、行动方案。
- 本地人物：当前对话中已提供的人物基础资料和已知盘面。
- 案例实践：邓焱、邓秀龙、张乖平等已出报告案例。
- 纠偏记录：张乖平生日修正、邓秀龙时辰补充。
- 质检模板：最高规格报告出具前检查项。
- 公开人物种子样本：已导入第一批 Wikidata 固定 QID 样本，用于验证公开样本管线。

## 导入公开人物种子

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\import_wikidata_seed.py
```

说明：

- 首批使用固定 QID 种子查询，避免在线 SPARQL 全库扫描过慢。
- 大规模 1000 万级采集不应依赖在线 SPARQL 全库查询，应使用 Wikidata dump 或分批索引策略。
- 当前导入写入 `public_persons`、`birth_facts` 和 `import_batches`。

## 按出生年份扩展样本

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\import_wikipedia_birth_year.py --year 1950 --limit 100
```

这条管线先读取 English Wikipedia 的 `Category:<year> births`，取页面对应的 Wikidata QID，再用 Wikidata API 导入结构化出生事实。它比在线 SPARQL 全库扫描更适合分批扩大。

按年份范围限速扩展：

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\import_wikipedia_year_range.py --start-year 1951 --end-year 1955 --limit 50 --pause-seconds 8
```

如果遇到 429 限流，脚本会退避等待，并把失败年份写入 `import_batches`，方便后续继续。

大范围批量扩展与断点续跑：

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\import_wikipedia_year_range_bulk.py --start-year 1000 --end-year 1549 --limit 25 --workers 6 --years-per-import 25 --fetch-source wikidata --reuse-cache
```

年度连续性审计：

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\audit_year_coverage.py --start-year 1000 --end-year 2007
```

当前个人级公开样本连续覆盖 1000—2007 年；2008 年以后涉及大量未成年人，不纳入个人级命理训练库。

## 生成命盘快照

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\calculate_chart_snapshots.py
```

有可靠时刻的资料生成四柱本地钟表时快照；无时辰资料只生成三柱。真太阳时、历史时区和 1582 年前历法仍作为独立边界标记，不会被静默忽略。

## 精度基础与报告闸门

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\build_precision_foundation.py
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\report_gate.py --subject-type local_person --subject-id P_DENG_XIN --module three_pillars --module precise_timing
```

闸门会给出 `allow`、`degrade` 或 `block`。L1/L2 不能请求时柱、子女晚年或精确应期；L3 只能生成暂定四柱报告；只有日期、精确时刻、地点、坐标、历史时区、历法转换均核验，且事件覆盖达标的 L4 才能进入结果规则校准。准入只证明资料够不够，不等于命理方法已经得到科学验证。

## 扩充可验证事件

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\enrich_wikidata_life_events.py --batch-size 500
```

只导入 Wikidata 声明中具有明确时间限定的事件。无日期的职业、婚姻、教育或奖项关系不作为事件时点使用。

公开出生地坐标回填：

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\enrich_wikidata_birthplaces.py --batch-size 500
```

时区实体引用会保存在地点 JSON 中，但只有确认到 IANA 时区及出生当年的法定时制后才写入 `timezone`；不会把模糊的时区名称直接当作可计算时区。

## 巡检

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\validate_database.py
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\db_stats.py
```

## 规则验证与偏差矩阵

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\evaluate_quality_rules.py
```

当前安全检查规则是“无时辰公开样本必须降级”。它只验证系统行为，不作为预测准确率。结果验证必须使用隔离的验证集和测试集，并要求同一人物至少有 5 个事件、3 种事件类型及 3 个有日期事件。

任何结果规则在运行前还必须登记验证协议：冻结规则版本、目标事件、预测时间窗、非命理基线、主指标、最小样本量和多重检验组。查看测试集后再改规则的结果只能进入新协议，不能回写成原协议命中。

## 设计边界

- 1000万人公开样本不会直接全部塞进小型仓库。
- 仓库保存 schema、脚本、小样本和本地验证库。
- 真正大规模采集应使用分批导入、外部存储和可复算流水线。
- 低精度公开样本只做宏观统计，不用于精细断事。
