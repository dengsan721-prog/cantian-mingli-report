DROP VIEW IF EXISTS v_database_counts;
CREATE VIEW v_database_counts AS
SELECT 'source_registry' AS table_name, COUNT(*) AS row_count FROM source_registry
UNION ALL SELECT 'theory_sources', COUNT(*) FROM theory_sources
UNION ALL SELECT 'knowledge_rules', COUNT(*) FROM knowledge_rules
UNION ALL SELECT 'local_persons', COUNT(*) FROM local_persons
UNION ALL SELECT 'public_persons', COUNT(*) FROM public_persons
UNION ALL SELECT 'birth_facts', COUNT(*) FROM birth_facts
UNION ALL SELECT 'chart_snapshots', COUNT(*) FROM chart_snapshots
UNION ALL SELECT 'life_events_public', COUNT(*) FROM life_events_public
UNION ALL SELECT 'case_studies', COUNT(*) FROM case_studies
UNION ALL SELECT 'correction_records', COUNT(*) FROM correction_records
UNION ALL SELECT 'rule_evaluations', COUNT(*) FROM rule_evaluations
UNION ALL SELECT 'bias_matrices', COUNT(*) FROM bias_matrices
UNION ALL SELECT 'data_quality_assessments', COUNT(*) FROM data_quality_assessments
UNION ALL SELECT 'validation_assignments', COUNT(*) FROM validation_assignments
UNION ALL SELECT 'validation_metrics', COUNT(*) FROM validation_metrics
UNION ALL SELECT 'validation_protocols', COUNT(*) FROM validation_protocols
UNION ALL SELECT 'report_runs', COUNT(*) FROM report_runs
UNION ALL SELECT 'report_claims', COUNT(*) FROM report_claims
UNION ALL SELECT 'import_batches', COUNT(*) FROM import_batches;

DROP VIEW IF EXISTS v_public_person_quality;
CREATE VIEW v_public_person_quality AS
SELECT
  quality_level,
  COUNT(*) AS person_count
FROM public_persons
GROUP BY quality_level;

DROP VIEW IF EXISTS v_birth_fact_precision;
CREATE VIEW v_birth_fact_precision AS
SELECT
  subject_type,
  date_precision,
  time_precision,
  COUNT(*) AS fact_count
FROM birth_facts
GROUP BY subject_type, date_precision, time_precision;

DROP VIEW IF EXISTS v_rule_confidence;
CREATE VIEW v_rule_confidence AS
SELECT
  system,
  priority,
  validation_status,
  COUNT(*) AS rule_count,
  ROUND(AVG(confidence_score), 3) AS avg_confidence
FROM knowledge_rules
GROUP BY system, priority, validation_status;

DROP VIEW IF EXISTS v_recent_import_batches;
CREATE VIEW v_recent_import_batches AS
SELECT
  batch_id,
  source_id,
  batch_type,
  status,
  record_count,
  started_at,
  finished_at,
  notes
FROM import_batches
ORDER BY started_at DESC;

DROP VIEW IF EXISTS v_report_readiness;
CREATE VIEW v_report_readiness AS
SELECT
  subject_type,
  quality_level,
  max_report_level,
  COUNT(*) AS subject_count,
  ROUND(AVG(overall_score), 2) AS avg_overall_score
FROM data_quality_assessments
GROUP BY subject_type, quality_level, max_report_level;

DROP VIEW IF EXISTS v_validation_split_counts;
CREATE VIEW v_validation_split_counts AS
SELECT dataset_split, era_bucket, COUNT(*) AS person_count
FROM validation_assignments
GROUP BY dataset_split, era_bucket;
