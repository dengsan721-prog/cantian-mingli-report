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
- `scripts/calculate_chart_snapshots.py`：根据出生事实生成三柱级命盘快照。
- `scripts/db_stats.py`：输出数据库统计。
- `scripts/validate_database.py`：校验表结构、JSON 字段和外键。
- `data/mingli_validation.db`：本地 SQLite 数据库，由初始化脚本生成。

## 初始化

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' work\mingli-system\scripts\init_database.py --reset
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

## 设计边界

- 1000万人公开样本不会直接全部塞进小型仓库。
- 仓库保存 schema、脚本、小样本和本地验证库。
- 真正大规模采集应使用分批导入、外部存储和可复算流水线。
- 低精度公开样本只做宏观统计，不用于精细断事。
