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
