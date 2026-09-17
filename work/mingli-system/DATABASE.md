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
- `scripts/calculate_chart_snapshots.py`：根据出生事实生成三柱级命盘快照。
- `scripts/evaluate_quality_rules.py`：生成初始规则验证记录和偏差矩阵。
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

当前快照只生成三柱级信息。无时辰样本不会进入时柱、大运应期等精细验证。

## 巡检

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\validate_database.py
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\db_stats.py
```

## 规则验证与偏差矩阵

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\evaluate_quality_rules.py
```

当前第一条自动验证规则是“无时辰公开样本必须降级”。它不验证命理结论本身，而是验证数据库不会把低精度样本误用于精细判断。

## 设计边界

- 1000万人公开样本不会直接全部塞进小型仓库。
- 仓库保存 schema、脚本、小样本和本地验证库。
- 真正大规模采集应使用分批导入、外部存储和可复算流水线。
- 低精度公开样本只做宏观统计，不用于精细断事。
