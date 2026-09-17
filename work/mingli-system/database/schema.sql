PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_batches (
  batch_id TEXT PRIMARY KEY,
  source_id TEXT,
  batch_type TEXT NOT NULL,
  status TEXT NOT NULL,
  record_count INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS source_registry (
  source_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  title TEXT,
  url TEXT,
  license TEXT,
  source_type TEXT NOT NULL,
  allowed_fields_json TEXT NOT NULL DEFAULT '[]',
  forbidden_fields_json TEXT NOT NULL DEFAULT '[]',
  trust_level TEXT NOT NULL DEFAULT 'C',
  refresh_cycle TEXT NOT NULL DEFAULT 'manual',
  use_note TEXT,
  status TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS theory_sources (
  source_id TEXT PRIMARY KEY,
  tradition TEXT NOT NULL,
  source_type TEXT NOT NULL,
  topic TEXT NOT NULL,
  summary TEXT NOT NULL,
  applicable_modules_json TEXT NOT NULL DEFAULT '[]',
  limitations TEXT,
  confidence TEXT NOT NULL DEFAULT 'medium',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_rules (
  rule_id TEXT PRIMARY KEY,
  system TEXT NOT NULL,
  topic TEXT NOT NULL,
  rule_summary TEXT NOT NULL,
  usage_scope TEXT NOT NULL,
  priority TEXT NOT NULL,
  conflict_policy TEXT NOT NULL,
  source_ids_json TEXT NOT NULL DEFAULT '[]',
  applicable_conditions_json TEXT NOT NULL DEFAULT '[]',
  forbidden_conditions_json TEXT NOT NULL DEFAULT '[]',
  validation_status TEXT NOT NULL DEFAULT 'unverified',
  confidence_score REAL NOT NULL DEFAULT 0.5,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS local_persons (
  person_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  gender TEXT NOT NULL DEFAULT 'unknown',
  calendar_type TEXT NOT NULL,
  birth_year INTEGER,
  birth_month INTEGER,
  birth_day INTEGER,
  is_leap_lunar_month INTEGER,
  time_text TEXT,
  hour_branch TEXT,
  time_accuracy TEXT NOT NULL DEFAULT 'unknown',
  timezone TEXT,
  birthplace_json TEXT NOT NULL DEFAULT '{}',
  known_chart_json TEXT NOT NULL DEFAULT '{}',
  privacy_level TEXT NOT NULL DEFAULT 'local_private',
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public_persons (
  public_person_id TEXT PRIMARY KEY,
  wikidata_qid TEXT UNIQUE,
  wikipedia_page_id TEXT,
  viaf TEXT,
  isni TEXT,
  external_ids_json TEXT NOT NULL DEFAULT '{}',
  primary_name TEXT NOT NULL,
  native_name TEXT,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  language_labels_json TEXT NOT NULL DEFAULT '{}',
  gender TEXT NOT NULL DEFAULT 'unknown',
  is_living INTEGER,
  occupations_json TEXT NOT NULL DEFAULT '[]',
  fields_json TEXT NOT NULL DEFAULT '[]',
  countries_json TEXT NOT NULL DEFAULT '[]',
  privacy_class TEXT NOT NULL DEFAULT 'public_figure',
  source_ids_json TEXT NOT NULL DEFAULT '[]',
  quality_level TEXT NOT NULL DEFAULT 'L0',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS birth_facts (
  birth_fact_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL CHECK (subject_type IN ('local_person', 'public_person')),
  subject_id TEXT NOT NULL,
  raw_birth_text TEXT,
  date_standard TEXT,
  date_precision TEXT NOT NULL DEFAULT 'unknown',
  calendar_type TEXT NOT NULL DEFAULT 'unknown',
  calendar_model TEXT,
  calendar_verification_status TEXT NOT NULL DEFAULT 'unverified',
  time_text TEXT,
  time_precision TEXT NOT NULL DEFAULT 'unknown',
  time_standard_status TEXT NOT NULL DEFAULT 'unverified',
  place_raw TEXT,
  place_standard_json TEXT NOT NULL DEFAULT '{}',
  longitude REAL,
  latitude REAL,
  timezone TEXT,
  source_url TEXT,
  source_id TEXT,
  conflict_group_id TEXT,
  confidence TEXT NOT NULL DEFAULT 'medium',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS life_events_public (
  event_id TEXT PRIMARY KEY,
  public_person_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_date TEXT,
  event_precision TEXT NOT NULL DEFAULT 'unknown',
  event_summary TEXT NOT NULL,
  source_url TEXT,
  source_id TEXT,
  evidence_quote_short TEXT,
  confidence TEXT NOT NULL DEFAULT 'medium',
  sensitivity TEXT NOT NULL DEFAULT 'low',
  allowed_for_modeling INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (public_person_id) REFERENCES public_persons(public_person_id)
);

CREATE TABLE IF NOT EXISTS chart_snapshots (
  chart_snapshot_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL CHECK (subject_type IN ('local_person', 'public_person')),
  subject_id TEXT NOT NULL,
  calculation_level TEXT NOT NULL DEFAULT 'uncertain',
  year_pillar TEXT,
  month_pillar TEXT,
  day_pillar TEXT,
  hour_pillar TEXT,
  day_master TEXT,
  month_command TEXT,
  climate_tags_json TEXT NOT NULL DEFAULT '[]',
  ten_god_tags_json TEXT NOT NULL DEFAULT '[]',
  conflict_combination_tags_json TEXT NOT NULL DEFAULT '[]',
  details_json TEXT NOT NULL DEFAULT '{}',
  boundary_flags_json TEXT NOT NULL DEFAULT '[]',
  engine_version TEXT NOT NULL DEFAULT 'legacy',
  confidence TEXT NOT NULL DEFAULT 'C',
  calculation_notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS case_studies (
  case_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL DEFAULT 'local_person',
  subject_id TEXT NOT NULL,
  name TEXT NOT NULL,
  chart_snapshot_json TEXT NOT NULL DEFAULT '{}',
  model_tags_json TEXT NOT NULL DEFAULT '[]',
  report_ids_json TEXT NOT NULL DEFAULT '[]',
  known_life_events_json TEXT NOT NULL DEFAULT '[]',
  validation_status TEXT NOT NULL DEFAULT 'unverified',
  lessons_json TEXT NOT NULL DEFAULT '[]',
  similarity_keys_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS correction_records (
  correction_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL DEFAULT 'local_person',
  subject_id TEXT,
  case_id TEXT,
  correction_type TEXT NOT NULL,
  before_json TEXT NOT NULL DEFAULT '{}',
  after_json TEXT NOT NULL DEFAULT '{}',
  reason TEXT NOT NULL,
  impact TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (case_id) REFERENCES case_studies(case_id)
);

CREATE TABLE IF NOT EXISTS report_quality_checks (
  check_id TEXT PRIMARY KEY,
  report_id TEXT,
  subject_type TEXT NOT NULL DEFAULT 'local_person',
  subject_id TEXT NOT NULL,
  items_json TEXT NOT NULL DEFAULT '{}',
  quality_grade TEXT NOT NULL DEFAULT 'C',
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rule_evaluations (
  evaluation_id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL,
  public_person_id TEXT NOT NULL,
  chart_snapshot_id TEXT,
  expected_pattern TEXT NOT NULL,
  observed_events_json TEXT NOT NULL DEFAULT '[]',
  match_level TEXT NOT NULL DEFAULT 'not_enough_data',
  mismatch_reason TEXT,
  confidence TEXT NOT NULL DEFAULT 'low',
  review_method TEXT NOT NULL DEFAULT 'automatic',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rule_id) REFERENCES knowledge_rules(rule_id),
  FOREIGN KEY (public_person_id) REFERENCES public_persons(public_person_id)
);

CREATE TABLE IF NOT EXISTS bias_matrices (
  matrix_id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL,
  sample_size INTEGER NOT NULL DEFAULT 0,
  hit_rate REAL NOT NULL DEFAULT 0,
  partial_hit_rate REAL NOT NULL DEFAULT 0,
  miss_rate REAL NOT NULL DEFAULT 0,
  reverse_hit_rate REAL NOT NULL DEFAULT 0,
  not_enough_data_rate REAL NOT NULL DEFAULT 1,
  stable_conditions_json TEXT NOT NULL DEFAULT '[]',
  failure_conditions_json TEXT NOT NULL DEFAULT '[]',
  recommended_report_policy TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rule_id) REFERENCES knowledge_rules(rule_id)
);

CREATE TABLE IF NOT EXISTS model_feedback_updates (
  update_id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL,
  before_policy_json TEXT NOT NULL DEFAULT '{}',
  after_policy_json TEXT NOT NULL DEFAULT '{}',
  reason TEXT NOT NULL,
  supporting_matrix_ids_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rule_id) REFERENCES knowledge_rules(rule_id)
);

CREATE TABLE IF NOT EXISTS data_quality_assessments (
  assessment_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL CHECK (subject_type IN ('local_person', 'public_person')),
  subject_id TEXT NOT NULL,
  birth_score INTEGER NOT NULL DEFAULT 0 CHECK (birth_score BETWEEN 0 AND 100),
  event_score INTEGER NOT NULL DEFAULT 0 CHECK (event_score BETWEEN 0 AND 100),
  source_score INTEGER NOT NULL DEFAULT 0 CHECK (source_score BETWEEN 0 AND 100),
  overall_score INTEGER NOT NULL DEFAULT 0 CHECK (overall_score BETWEEN 0 AND 100),
  quality_level TEXT NOT NULL DEFAULT 'L0',
  max_report_level TEXT NOT NULL DEFAULT 'intake_only',
  allowed_modules_json TEXT NOT NULL DEFAULT '[]',
  blocked_modules_json TEXT NOT NULL DEFAULT '[]',
  reason_codes_json TEXT NOT NULL DEFAULT '[]',
  assessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (subject_type, subject_id)
);

CREATE TABLE IF NOT EXISTS validation_assignments (
  public_person_id TEXT PRIMARY KEY,
  split_version TEXT NOT NULL,
  dataset_split TEXT NOT NULL CHECK (dataset_split IN ('train', 'validation', 'test')),
  era_bucket TEXT NOT NULL DEFAULT 'unknown',
  assignment_hash TEXT NOT NULL,
  assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (public_person_id) REFERENCES public_persons(public_person_id)
);

CREATE TABLE IF NOT EXISTS validation_metrics (
  metric_id TEXT PRIMARY KEY,
  rule_id TEXT,
  metric_type TEXT NOT NULL,
  dataset_split TEXT NOT NULL,
  sample_size INTEGER NOT NULL DEFAULT 0,
  observed_rate REAL,
  baseline_rate REAL,
  lift REAL,
  confidence_interval_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'not_evaluable',
  notes TEXT,
  calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rule_id) REFERENCES knowledge_rules(rule_id)
);

CREATE TABLE IF NOT EXISTS validation_protocols (
  protocol_id TEXT PRIMARY KEY,
  rule_id TEXT,
  protocol_type TEXT NOT NULL CHECK (protocol_type IN ('safety', 'outcome')),
  hypothesis TEXT NOT NULL,
  cohort_definition_json TEXT NOT NULL DEFAULT '{}',
  target_event_types_json TEXT NOT NULL DEFAULT '[]',
  forecast_window_json TEXT NOT NULL DEFAULT '{}',
  baseline_spec_json TEXT NOT NULL DEFAULT '{}',
  primary_metric TEXT NOT NULL,
  minimum_sample_size INTEGER NOT NULL,
  split_version TEXT NOT NULL,
  frozen_rule_version TEXT NOT NULL,
  multiple_testing_family TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  preregistered_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rule_id) REFERENCES knowledge_rules(rule_id)
);

CREATE TABLE IF NOT EXISTS report_runs (
  report_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL CHECK (subject_type IN ('local_person', 'public_person')),
  subject_id TEXT NOT NULL,
  chart_snapshot_id TEXT,
  model_version TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  max_report_level TEXT NOT NULL,
  quality_grade TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'generated',
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (chart_snapshot_id) REFERENCES chart_snapshots(chart_snapshot_id)
);

CREATE TABLE IF NOT EXISTS report_claims (
  claim_id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  module TEXT NOT NULL,
  claim_summary TEXT NOT NULL,
  rule_ids_json TEXT NOT NULL DEFAULT '[]',
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  confidence TEXT NOT NULL DEFAULT 'low',
  conclusion_type TEXT NOT NULL DEFAULT 'conditional',
  validation_state TEXT NOT NULL DEFAULT 'unverified',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (report_id) REFERENCES report_runs(report_id)
);

CREATE INDEX IF NOT EXISTS idx_public_persons_wikidata ON public_persons(wikidata_qid);
CREATE INDEX IF NOT EXISTS idx_public_persons_quality ON public_persons(quality_level);
CREATE INDEX IF NOT EXISTS idx_birth_facts_subject ON birth_facts(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_life_events_person ON life_events_public(public_person_id);
CREATE INDEX IF NOT EXISTS idx_life_events_type_date ON life_events_public(event_type, event_date);
CREATE INDEX IF NOT EXISTS idx_chart_snapshots_subject ON chart_snapshots(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_case_studies_subject ON case_studies(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_correction_subject ON correction_records(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_rule_eval_rule ON rule_evaluations(rule_id);
CREATE INDEX IF NOT EXISTS idx_rule_eval_person ON rule_evaluations(public_person_id);
CREATE INDEX IF NOT EXISTS idx_quality_subject ON data_quality_assessments(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_quality_level ON data_quality_assessments(quality_level, max_report_level);
CREATE INDEX IF NOT EXISTS idx_validation_split ON validation_assignments(dataset_split);
CREATE INDEX IF NOT EXISTS idx_validation_metric_rule ON validation_metrics(rule_id, dataset_split);
CREATE INDEX IF NOT EXISTS idx_validation_protocol_rule ON validation_protocols(rule_id, status);
CREATE INDEX IF NOT EXISTS idx_report_run_subject ON report_runs(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_report_claim_report ON report_claims(report_id);
