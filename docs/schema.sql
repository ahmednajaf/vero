BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE companies (
    company_name VARCHAR(240) NOT NULL, 
    ticker VARCHAR(32) NOT NULL, 
    country VARCHAR(2) NOT NULL, 
    region VARCHAR(80) NOT NULL, 
    exchange VARCHAR(32) NOT NULL, 
    index VARCHAR(160), 
    sector VARCHAR(80) NOT NULL, 
    industry VARCHAR(160) NOT NULL, 
    official_domain VARCHAR(253) NOT NULL, 
    investor_relations_url TEXT, 
    sustainability_url TEXT, 
    reporting_currency VARCHAR(3), 
    revenue NUMERIC(30, 6), 
    revenue_year INTEGER, 
    reporting_year INTEGER NOT NULL, 
    market_cap NUMERIC(30, 6), 
    active BOOLEAN DEFAULT true NOT NULL, 
    source_file TEXT, 
    source_row INTEGER, 
    source_sha256 VARCHAR(64), 
    imported_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_companies PRIMARY KEY (id), 
    CONSTRAINT ck_companies_identity_not_blank CHECK (btrim(company_name) <> '' AND btrim(ticker) <> '' AND btrim(exchange) <> ''), 
    CONSTRAINT ck_companies_country_code CHECK (country ~ '^[A-Z]{2}$'), 
    CONSTRAINT ck_companies_market_cap_context CHECK (market_cap IS NULL OR (market_cap >= 0 AND market_cap <> 'NaN'::numeric AND reporting_currency IS NOT NULL)), 
    CONSTRAINT ck_companies_currency_code CHECK (reporting_currency IS NULL OR reporting_currency ~ '^[A-Z]{3}$'), 
    CONSTRAINT ck_companies_revenue_context CHECK (revenue IS NULL OR (revenue >= 0 AND revenue <> 'NaN'::numeric AND revenue_year IS NOT NULL AND reporting_currency IS NOT NULL)), 
    CONSTRAINT ck_companies_sector CHECK (sector IN ('Financial Services','Technology','Energy','Consumer / Retail','Industrials')), 
    CONSTRAINT ck_companies_reporting_year CHECK (reporting_year BETWEEN 2000 AND 2100), 
    CONSTRAINT ck_companies_revenue_year CHECK (revenue_year IS NULL OR revenue_year BETWEEN 1900 AND 2100)
);

CREATE INDEX ix_companies_cycle_active ON companies (reporting_year, active);

CREATE INDEX ix_companies_name ON companies (lower(company_name), id);

CREATE INDEX ix_companies_sector_country ON companies (sector, country);

CREATE UNIQUE INDEX uq_companies_listing ON companies (lower(exchange), lower(ticker));

CREATE TABLE metric_definitions (
    metric_code VARCHAR(100) NOT NULL, 
    definition_version INTEGER NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    description TEXT NOT NULL, 
    sector_applicability JSONB NOT NULL, 
    quantity_kind VARCHAR(32) NOT NULL, 
    canonical_unit VARCHAR(80) NOT NULL, 
    value_type VARCHAR(32) NOT NULL, 
    directionality VARCHAR(32) NOT NULL, 
    scope VARCHAR(80) NOT NULL, 
    required_comparison_dimensions JSONB NOT NULL, 
    normalisation_rule_version VARCHAR(80), 
    validation_rule_version VARCHAR(80), 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_metric_definitions PRIMARY KEY (id), 
    CONSTRAINT uq_metric_definitions_metric_code UNIQUE (metric_code, definition_version)
);

CREATE TABLE themes (
    theme_code VARCHAR(100) NOT NULL, 
    taxonomy_version INTEGER NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    description TEXT NOT NULL, 
    parent_theme_id UUID, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_themes PRIMARY KEY (id), 
    CONSTRAINT fk_themes_parent_theme_id_themes FOREIGN KEY(parent_theme_id) REFERENCES themes (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_themes_theme_code UNIQUE (theme_code, taxonomy_version)
);

CREATE INDEX ix_themes_parent_theme_id ON themes (parent_theme_id);

CREATE TABLE reports (
    company_id UUID NOT NULL, 
    title TEXT NOT NULL, 
    report_type VARCHAR(40) NOT NULL, 
    reporting_year INTEGER NOT NULL, 
    period_start DATE, 
    period_end DATE, 
    publication_date DATE, 
    language_code VARCHAR(10) DEFAULT 'en' NOT NULL, 
    source_url TEXT NOT NULL, 
    final_url TEXT, 
    discovered_from_url TEXT, 
    retrieved_at TIMESTAMP WITH TIME ZONE, 
    storage_key TEXT, 
    content_sha256 VARCHAR(64), 
    file_size_bytes INTEGER, 
    page_count INTEGER, 
    document_version INTEGER DEFAULT '1' NOT NULL, 
    supersedes_report_id UUID, 
    download_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
    parse_status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
    notes TEXT DEFAULT '' NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_reports PRIMARY KEY (id), 
    CONSTRAINT ck_reports_source_required CHECK (btrim(source_url) <> ''), 
    CONSTRAINT ck_reports_checksum CHECK (content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'), 
    CONSTRAINT ck_reports_file_size CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0), 
    CONSTRAINT ck_reports_page_count CHECK (page_count IS NULL OR page_count > 0), 
    CONSTRAINT ck_reports_period CHECK (period_end >= period_start), 
    CONSTRAINT ck_reports_year CHECK (reporting_year BETWEEN 1900 AND 2100), 
    CONSTRAINT ck_reports_no_self_supersession CHECK (supersedes_report_id IS NULL OR supersedes_report_id <> id), 
    CONSTRAINT fk_reports_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_reports_supersedes_report_id_reports FOREIGN KEY(supersedes_report_id, company_id) REFERENCES reports (id, company_id), 
    CONSTRAINT uq_reports_company_id UNIQUE (company_id, content_sha256), 
    CONSTRAINT uq_reports_company_identity UNIQUE (id, company_id)
);

CREATE INDEX ix_reports_company_year_type ON reports (company_id, reporting_year, report_type);

CREATE TABLE extraction_runs (
    report_id UUID NOT NULL, 
    parent_run_id UUID, 
    stage VARCHAR(32) NOT NULL, 
    status VARCHAR(32) DEFAULT 'queued' NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    input_sha256 VARCHAR(64) NOT NULL, 
    model_provider VARCHAR(80), 
    model_name VARCHAR(160), 
    model_digest VARCHAR(128), 
    prompt_version VARCHAR(80), 
    schema_version VARCHAR(80) NOT NULL, 
    code_version VARCHAR(80) NOT NULL, 
    parameters JSONB DEFAULT '{}'::jsonb NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    error_code VARCHAR(80), 
    error_summary TEXT, 
    output_summary JSONB, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_extraction_runs PRIMARY KEY (id), 
    CONSTRAINT ck_extraction_runs_stage CHECK (stage IN ('parsing','retrieval','extraction','normalisation','quality')), 
    CONSTRAINT ck_extraction_runs_status CHECK (status IN ('queued','running','succeeded','failed','cancelled')), 
    CONSTRAINT ck_extraction_runs_time_order CHECK (finished_at IS NULL OR finished_at >= started_at), 
    CONSTRAINT fk_extraction_runs_parent_run_id_extraction_runs FOREIGN KEY(parent_run_id) REFERENCES extraction_runs (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_extraction_runs_report_id_reports FOREIGN KEY(report_id) REFERENCES reports (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_runs_report_identity UNIQUE (id, report_id), 
    CONSTRAINT uq_extraction_runs_idempotency_key UNIQUE (idempotency_key)
);

CREATE INDEX ix_extraction_runs_parent_run_id ON extraction_runs (parent_run_id);

CREATE INDEX ix_runs_report_stage_status ON extraction_runs (report_id, stage, status);

CREATE TABLE document_chunks (
    report_id UUID NOT NULL, 
    parse_run_id UUID NOT NULL, 
    chunk_index INTEGER NOT NULL, 
    physical_page_start INTEGER NOT NULL, 
    physical_page_end INTEGER NOT NULL, 
    printed_page_label VARCHAR(80), 
    section_title TEXT, 
    text TEXT NOT NULL, 
    text_sha256 VARCHAR(64) NOT NULL, 
    chunk_type VARCHAR(16) NOT NULL, 
    parser_name VARCHAR(80) NOT NULL, 
    parser_version VARCHAR(80) NOT NULL, 
    table_metadata JSONB, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_document_chunks PRIMARY KEY (id), 
    CONSTRAINT ck_document_chunks_type CHECK (chunk_type IN ('text','table')), 
    CONSTRAINT ck_document_chunks_chunk_index CHECK (chunk_index >= 0), 
    CONSTRAINT ck_document_chunks_page_range CHECK (physical_page_start >= 1 AND physical_page_end >= physical_page_start), 
    CONSTRAINT fk_document_chunks_parse_run_id_extraction_runs FOREIGN KEY(parse_run_id, report_id) REFERENCES extraction_runs (id, report_id), 
    CONSTRAINT fk_document_chunks_report_id_reports FOREIGN KEY(report_id) REFERENCES reports (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_chunks_report_identity UNIQUE (id, report_id), 
    CONSTRAINT uq_document_chunks_report_id UNIQUE (report_id, parse_run_id, chunk_index)
);

CREATE INDEX ix_chunks_parse_run ON document_chunks (parse_run_id);

CREATE INDEX ix_chunks_report_page ON document_chunks (report_id, physical_page_start);

CREATE TABLE company_themes (
    theme_id UUID NOT NULL, 
    company_id UUID NOT NULL, 
    report_id UUID NOT NULL, 
    document_chunk_id UUID NOT NULL, 
    extraction_run_id UUID, 
    reporting_year INTEGER NOT NULL, 
    source_url TEXT NOT NULL, 
    source_physical_page INTEGER NOT NULL, 
    source_printed_page_label VARCHAR(80), 
    supporting_excerpt TEXT NOT NULL, 
    extraction_method VARCHAR(80) NOT NULL, 
    confidence NUMERIC(5, 4), 
    confidence_notes TEXT, 
    validation_state VARCHAR(32) DEFAULT 'extracted' NOT NULL, 
    notes TEXT DEFAULT '' NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_company_themes PRIMARY KEY (id), 
    CONSTRAINT ck_company_themes_evidence_required CHECK (btrim(source_url) <> '' AND btrim(supporting_excerpt) <> '' AND btrim(extraction_method) <> ''), 
    CONSTRAINT ck_company_themes_confidence CHECK ((confidence IS NOT NULL AND confidence BETWEEN 0 AND 1) OR (confidence IS NULL AND confidence_notes IS NOT NULL AND btrim(confidence_notes) <> '')), 
    CONSTRAINT ck_company_themes_validation_state CHECK (validation_state IN ('extracted','validated','needs_review','not_reported','not_comparable','rejected')), 
    CONSTRAINT ck_company_themes_year CHECK (reporting_year BETWEEN 1900 AND 2100), 
    CONSTRAINT ck_company_themes_page CHECK (source_physical_page >= 1), 
    CONSTRAINT fk_company_themes_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_company_themes_document_chunk_id_document_chunks FOREIGN KEY(document_chunk_id, report_id) REFERENCES document_chunks (id, report_id), 
    CONSTRAINT fk_company_themes_extraction_run_id_extraction_runs FOREIGN KEY(extraction_run_id, report_id) REFERENCES extraction_runs (id, report_id), 
    CONSTRAINT fk_company_themes_report_id_reports FOREIGN KEY(report_id, company_id) REFERENCES reports (id, company_id), 
    CONSTRAINT fk_company_themes_theme_id_themes FOREIGN KEY(theme_id) REFERENCES themes (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_company_themes_company_id UNIQUE (company_id, theme_id, reporting_year, document_chunk_id)
);

CREATE INDEX ix_company_themes_chunk ON company_themes (document_chunk_id);

CREATE INDEX ix_company_themes_report ON company_themes (report_id);

CREATE INDEX ix_company_themes_run ON company_themes (extraction_run_id);

CREATE INDEX ix_company_themes_theme_year ON company_themes (theme_id, reporting_year);

CREATE TABLE metric_observations (
    metric_definition_id UUID NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    period_start DATE, 
    period_end DATE, 
    raw_value TEXT, 
    raw_unit TEXT, 
    normalised_value NUMERIC(38, 12), 
    normalised_unit VARCHAR(80), 
    value_qualifier VARCHAR(24) DEFAULT 'exact' NOT NULL, 
    normalisation_rule_version VARCHAR(80), 
    organisational_boundary TEXT, 
    consolidation_basis VARCHAR(80), 
    scope VARCHAR(80), 
    scope2_method VARCHAR(40), 
    scope3_categories JSONB, 
    intensity_denominator TEXT, 
    denominator_unit VARCHAR(80), 
    currency_code VARCHAR(3), 
    currency_basis TEXT, 
    coverage_description TEXT, 
    methodology_version VARCHAR(80), 
    is_historical_comparative BOOLEAN DEFAULT false NOT NULL, 
    is_restated BOOLEAN DEFAULT false NOT NULL, 
    supersedes_observation_id UUID, 
    compatibility_state VARCHAR(32) DEFAULT 'unchecked' NOT NULL, 
    compatibility_rule_version VARCHAR(80), 
    comparison_group_key VARCHAR(200), 
    company_id UUID NOT NULL, 
    report_id UUID NOT NULL, 
    document_chunk_id UUID NOT NULL, 
    extraction_run_id UUID, 
    reporting_year INTEGER NOT NULL, 
    source_url TEXT NOT NULL, 
    source_physical_page INTEGER NOT NULL, 
    source_printed_page_label VARCHAR(80), 
    supporting_excerpt TEXT NOT NULL, 
    extraction_method VARCHAR(80) NOT NULL, 
    confidence NUMERIC(5, 4), 
    confidence_notes TEXT, 
    validation_state VARCHAR(32) DEFAULT 'extracted' NOT NULL, 
    notes TEXT DEFAULT '' NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_metric_observations PRIMARY KEY (id), 
    CONSTRAINT ck_metric_observations_evidence_required CHECK (btrim(source_url) <> '' AND btrim(supporting_excerpt) <> '' AND btrim(extraction_method) <> ''), 
    CONSTRAINT ck_metric_observations_confidence CHECK ((confidence IS NOT NULL AND confidence BETWEEN 0 AND 1) OR (confidence IS NULL AND confidence_notes IS NOT NULL AND btrim(confidence_notes) <> '')), 
    CONSTRAINT ck_metric_observations_normalised_provenance CHECK (normalised_value IS NULL OR (normalised_value <> 'NaN'::numeric AND normalised_unit IS NOT NULL AND raw_value IS NOT NULL AND raw_unit IS NOT NULL AND normalisation_rule_version IS NOT NULL)), 
    CONSTRAINT ck_metric_observations_missing_is_not_zero CHECK (validation_state <> 'not_reported' OR (raw_value IS NULL AND normalised_value IS NULL)), 
    CONSTRAINT ck_metric_observations_validation_state CHECK (validation_state IN ('extracted','validated','needs_review','not_reported','not_comparable','rejected')), 
    CONSTRAINT ck_metric_observations_value_required CHECK (validation_state NOT IN ('extracted','validated','not_comparable') OR (raw_value IS NOT NULL AND btrim(raw_value) <> '')), 
    CONSTRAINT ck_metric_observations_qualifier CHECK (value_qualifier IN ('exact','approximate','less_than','greater_than','range')), 
    CONSTRAINT ck_metric_observations_period CHECK (period_end >= period_start), 
    CONSTRAINT ck_metric_observations_year CHECK (reporting_year BETWEEN 1900 AND 2100), 
    CONSTRAINT ck_metric_observations_page CHECK (source_physical_page >= 1), 
    CONSTRAINT fk_metric_observations_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_metric_observations_document_chunk_id_document_chunks FOREIGN KEY(document_chunk_id, report_id) REFERENCES document_chunks (id, report_id), 
    CONSTRAINT fk_metric_observations_extraction_run_id_extraction_runs FOREIGN KEY(extraction_run_id, report_id) REFERENCES extraction_runs (id, report_id), 
    CONSTRAINT fk_metric_observations_metric_definition_id_metric_definitions FOREIGN KEY(metric_definition_id) REFERENCES metric_definitions (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_metric_observations_report_id_reports FOREIGN KEY(report_id, company_id) REFERENCES reports (id, company_id), 
    CONSTRAINT fk_metric_observations_supersedes_observation_id_metric_60a3 FOREIGN KEY(supersedes_observation_id) REFERENCES metric_observations (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_metric_observations_idempotency_key UNIQUE (idempotency_key)
);

CREATE INDEX ix_metric_observations_chunk ON metric_observations (document_chunk_id);

CREATE INDEX ix_metric_observations_report ON metric_observations (report_id);

CREATE INDEX ix_metric_observations_run ON metric_observations (extraction_run_id);

CREATE INDEX ix_metric_observations_supersedes_observation_id ON metric_observations (supersedes_observation_id);

CREATE INDEX ix_observations_company_year_metric_state ON metric_observations (company_id, reporting_year, metric_definition_id, validation_state);

CREATE INDEX ix_observations_metric_year_group ON metric_observations (metric_definition_id, reporting_year, comparison_group_key);

CREATE TABLE targets (
    metric_definition_id UUID NOT NULL, 
    target_type VARCHAR(40) NOT NULL, 
    baseline_year INTEGER, 
    baseline_raw_value TEXT, 
    baseline_raw_unit TEXT, 
    baseline_normalised_value NUMERIC(38, 12), 
    baseline_normalised_unit VARCHAR(80), 
    target_year INTEGER NOT NULL, 
    target_raw_value TEXT, 
    target_raw_unit TEXT, 
    target_normalised_value NUMERIC(38, 12), 
    target_normalised_unit VARCHAR(80), 
    normalisation_rule_version VARCHAR(80), 
    reduction_percent NUMERIC(7, 4), 
    organisational_boundary TEXT, 
    scope VARCHAR(80), 
    scope2_method VARCHAR(40), 
    scope3_categories JSONB, 
    target_coverage TEXT, 
    company_id UUID NOT NULL, 
    report_id UUID NOT NULL, 
    document_chunk_id UUID NOT NULL, 
    extraction_run_id UUID, 
    reporting_year INTEGER NOT NULL, 
    source_url TEXT NOT NULL, 
    source_physical_page INTEGER NOT NULL, 
    source_printed_page_label VARCHAR(80), 
    supporting_excerpt TEXT NOT NULL, 
    extraction_method VARCHAR(80) NOT NULL, 
    confidence NUMERIC(5, 4), 
    confidence_notes TEXT, 
    validation_state VARCHAR(32) DEFAULT 'extracted' NOT NULL, 
    notes TEXT DEFAULT '' NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_targets PRIMARY KEY (id), 
    CONSTRAINT ck_targets_evidence_required CHECK (btrim(source_url) <> '' AND btrim(supporting_excerpt) <> '' AND btrim(extraction_method) <> ''), 
    CONSTRAINT ck_targets_confidence CHECK ((confidence IS NOT NULL AND confidence BETWEEN 0 AND 1) OR (confidence IS NULL AND confidence_notes IS NOT NULL AND btrim(confidence_notes) <> '')), 
    CONSTRAINT ck_targets_validation_state CHECK (validation_state IN ('extracted','validated','needs_review','not_reported','not_comparable','rejected')), 
    CONSTRAINT ck_targets_baseline_provenance CHECK (baseline_normalised_value IS NULL OR (baseline_raw_value IS NOT NULL AND baseline_raw_unit IS NOT NULL AND baseline_normalised_unit IS NOT NULL AND baseline_year IS NOT NULL AND normalisation_rule_version IS NOT NULL)), 
    CONSTRAINT ck_targets_baseline_year CHECK (baseline_year IS NULL OR (baseline_year BETWEEN 1900 AND 2200 AND baseline_year <= target_year)), 
    CONSTRAINT ck_targets_reduction_percent CHECK (reduction_percent IS NULL OR reduction_percent BETWEEN 0 AND 100), 
    CONSTRAINT ck_targets_year CHECK (reporting_year BETWEEN 1900 AND 2100), 
    CONSTRAINT ck_targets_page CHECK (source_physical_page >= 1), 
    CONSTRAINT ck_targets_target_provenance CHECK (target_normalised_value IS NULL OR (target_raw_value IS NOT NULL AND target_raw_unit IS NOT NULL AND target_normalised_unit IS NOT NULL AND normalisation_rule_version IS NOT NULL)), 
    CONSTRAINT ck_targets_target_year CHECK (target_year BETWEEN 1900 AND 2200), 
    CONSTRAINT fk_targets_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_targets_document_chunk_id_document_chunks FOREIGN KEY(document_chunk_id, report_id) REFERENCES document_chunks (id, report_id), 
    CONSTRAINT fk_targets_extraction_run_id_extraction_runs FOREIGN KEY(extraction_run_id, report_id) REFERENCES extraction_runs (id, report_id), 
    CONSTRAINT fk_targets_metric_definition_id_metric_definitions FOREIGN KEY(metric_definition_id) REFERENCES metric_definitions (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_targets_report_id_reports FOREIGN KEY(report_id, company_id) REFERENCES reports (id, company_id)
);

CREATE INDEX ix_targets_chunk ON targets (document_chunk_id);

CREATE INDEX ix_targets_company_year_metric ON targets (company_id, reporting_year, metric_definition_id);

CREATE INDEX ix_targets_metric ON targets (metric_definition_id);

CREATE INDEX ix_targets_report ON targets (report_id);

CREATE INDEX ix_targets_run ON targets (extraction_run_id);

CREATE TABLE validation_events (
    id UUID NOT NULL, 
    metric_observation_id UUID, 
    target_id UUID, 
    company_theme_id UUID, 
    previous_state VARCHAR(32), 
    new_state VARCHAR(32) NOT NULL, 
    rule_code VARCHAR(80), 
    rule_version VARCHAR(80), 
    actor_type VARCHAR(16) NOT NULL, 
    actor_reference VARCHAR(160) NOT NULL, 
    reason TEXT NOT NULL, 
    details JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_validation_events PRIMARY KEY (id), 
    CONSTRAINT ck_validation_events_actor_type CHECK (actor_type IN ('rule','human')), 
    CONSTRAINT ck_validation_events_attribution CHECK (btrim(reason) <> '' AND btrim(actor_reference) <> ''), 
    CONSTRAINT ck_validation_events_new_state CHECK (new_state IN ('extracted','validated','needs_review','not_reported','not_comparable','rejected')), 
    CONSTRAINT ck_validation_events_previous_state CHECK (previous_state IS NULL OR previous_state IN ('extracted','validated','needs_review','not_reported','not_comparable','rejected')), 
    CONSTRAINT ck_validation_events_exactly_one_subject CHECK (num_nonnulls(metric_observation_id, target_id, company_theme_id) = 1), 
    CONSTRAINT fk_validation_events_company_theme_id_company_themes FOREIGN KEY(company_theme_id) REFERENCES company_themes (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_validation_events_metric_observation_id_metric_observations FOREIGN KEY(metric_observation_id) REFERENCES metric_observations (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_validation_events_target_id_targets FOREIGN KEY(target_id) REFERENCES targets (id) ON DELETE RESTRICT
);

CREATE INDEX ix_validation_observation_time ON validation_events (metric_observation_id, created_at);

CREATE INDEX ix_validation_target_time ON validation_events (target_id, created_at);

CREATE INDEX ix_validation_theme_time ON validation_events (company_theme_id, created_at);

CREATE FUNCTION sbi_touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN NEW.updated_at = clock_timestamp(); RETURN NEW; END;
        $$;

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON companies FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON reports FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON document_chunks FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON metric_definitions FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON metric_observations FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON targets FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON themes FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON company_themes FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON extraction_runs FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE FUNCTION sbi_protect_validation_history() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'validation_events are append-only' USING ERRCODE = '23514'; END;
        $$;

CREATE TRIGGER validation_history_immutable BEFORE UPDATE OR DELETE ON validation_events FOR EACH ROW EXECUTE FUNCTION sbi_protect_validation_history();

CREATE FUNCTION sbi_check_evidence_page() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE first_page integer; last_page integer;
        BEGIN
          SELECT physical_page_start, physical_page_end INTO first_page, last_page
          FROM document_chunks WHERE id = NEW.document_chunk_id AND report_id = NEW.report_id;
          IF first_page IS NOT NULL AND
             (NEW.source_physical_page < first_page OR NEW.source_physical_page > last_page) THEN
            RAISE EXCEPTION 'Source page is outside its evidence chunk' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;

CREATE TRIGGER evidence_page BEFORE INSERT OR UPDATE ON metric_observations FOR EACH ROW EXECUTE FUNCTION sbi_check_evidence_page();

CREATE TRIGGER evidence_page BEFORE INSERT OR UPDATE ON targets FOR EACH ROW EXECUTE FUNCTION sbi_check_evidence_page();

CREATE TRIGGER evidence_page BEFORE INSERT OR UPDATE ON company_themes FOR EACH ROW EXECUTE FUNCTION sbi_check_evidence_page();

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> f0b2edabe086

CREATE TABLE report_artifacts (
    content_sha256 VARCHAR(64) NOT NULL, 
    storage_key TEXT NOT NULL, 
    file_size_bytes INTEGER NOT NULL, 
    mime_type VARCHAR(120) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_report_artifacts PRIMARY KEY (id), 
    CONSTRAINT ck_report_artifacts_checksum CHECK (content_sha256 ~ '^[0-9a-f]{64}$'), 
    CONSTRAINT ck_report_artifacts_file_size CHECK (file_size_bytes > 0), 
    CONSTRAINT uq_report_artifacts_content_sha256 UNIQUE (content_sha256), 
    CONSTRAINT uq_report_artifacts_storage_key UNIQUE (storage_key)
);

CREATE TABLE report_discovery_runs (
    company_id UUID NOT NULL, 
    requested_year INTEGER NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    selection_reason TEXT NOT NULL, 
    policy_version VARCHAR(40) NOT NULL, 
    sources JSONB NOT NULL, 
    diagnostics JSONB NOT NULL, 
    pages_visited INTEGER DEFAULT '0' NOT NULL, 
    http_requests INTEGER DEFAULT '0' NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_report_discovery_runs PRIMARY KEY (id), 
    CONSTRAINT ck_report_discovery_runs_status CHECK (status IN ('discovered','downloaded','needs_review','unavailable','failed')), 
    CONSTRAINT ck_report_discovery_runs_requested_year CHECK (requested_year BETWEEN 2000 AND 2100), 
    CONSTRAINT fk_report_discovery_runs_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_discovery_run_company_year UNIQUE (id, company_id, requested_year)
);

CREATE INDEX ix_discovery_company_year_time ON report_discovery_runs (company_id, requested_year, created_at);

ALTER TABLE reports ADD COLUMN discovery_run_id UUID;

ALTER TABLE reports ADD COLUMN requested_year INTEGER;

ALTER TABLE reports ADD COLUMN detected_year INTEGER;

ALTER TABLE reports ADD COLUMN url_sha256 VARCHAR(64);

ALTER TABLE reports ADD COLUMN mime_type VARCHAR(120);

ALTER TABLE reports ADD COLUMN confidence NUMERIC(5, 4);

ALTER TABLE reports ADD COLUMN selection_reason TEXT;

ALTER TABLE reports ADD COLUMN status VARCHAR(24) DEFAULT 'discovered' NOT NULL;

ALTER TABLE reports ADD COLUMN is_selected BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE reports ADD COLUMN source_policy VARCHAR(40);

ALTER TABLE reports ADD COLUMN artifact_id UUID;

ALTER TABLE reports ALTER COLUMN reporting_year DROP NOT NULL;

ALTER TABLE reports DROP CONSTRAINT uq_reports_company_id;

CREATE INDEX ix_reports_artifact ON reports (artifact_id);

CREATE INDEX ix_reports_company_checksum ON reports (company_id, content_sha256);

CREATE INDEX ix_reports_discovery_status ON reports (requested_year, status, is_selected);

CREATE UNIQUE INDEX uq_reports_run_selected ON reports (discovery_run_id) WHERE is_selected AND discovery_run_id IS NOT NULL;

ALTER TABLE reports ADD CONSTRAINT uq_reports_run_url UNIQUE (discovery_run_id, url_sha256);

ALTER TABLE reports ADD CONSTRAINT fk_reports_discovery_run_id_report_discovery_runs FOREIGN KEY(discovery_run_id, company_id, requested_year) REFERENCES report_discovery_runs (id, company_id, requested_year);

ALTER TABLE reports ADD CONSTRAINT fk_reports_artifact_id_report_artifacts FOREIGN KEY(artifact_id) REFERENCES report_artifacts (id) ON DELETE RESTRICT;

ALTER TABLE reports ADD CONSTRAINT ck_reports_discovery_status CHECK (status IN ('discovered','downloaded','needs_review','unavailable','failed'));

ALTER TABLE reports ADD CONSTRAINT ck_reports_discovery_confidence CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1);

ALTER TABLE reports ADD CONSTRAINT ck_reports_requested_year CHECK (requested_year IS NULL OR requested_year BETWEEN 2000 AND 2100);

ALTER TABLE reports ADD CONSTRAINT ck_reports_detected_year CHECK (detected_year IS NULL OR detected_year BETWEEN 1900 AND 2100);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON report_artifacts FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON report_discovery_runs FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

UPDATE alembic_version SET version_num='f0b2edabe086' WHERE alembic_version.version_num = '0001';

-- Running upgrade f0b2edabe086 -> 53487b8db383

CREATE TABLE document_pages (
    report_id UUID NOT NULL, 
    parse_run_id UUID NOT NULL, 
    page_number INTEGER NOT NULL, 
    printed_page_label VARCHAR(80), 
    width_points FLOAT NOT NULL, 
    height_points FLOAT NOT NULL, 
    rotation INTEGER NOT NULL, 
    raw_text TEXT NOT NULL, 
    raw_text_sha256 VARCHAR(64) NOT NULL, 
    ordered_text TEXT NOT NULL, 
    ordered_text_sha256 VARCHAR(64) NOT NULL, 
    text_characters INTEGER NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    headings JSONB NOT NULL, 
    layout JSONB NOT NULL, 
    warnings JSONB NOT NULL, 
    parser_name VARCHAR(80) NOT NULL, 
    parser_version VARCHAR(80) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_document_pages PRIMARY KEY (id), 
    CONSTRAINT ck_document_pages_hashes CHECK (raw_text_sha256 ~ '^[0-9a-f]{64}$' AND ordered_text_sha256 ~ '^[0-9a-f]{64}$'), 
    CONSTRAINT ck_document_pages_status CHECK (status IN ('parsed','needs_ocr','failed')), 
    CONSTRAINT ck_document_pages_page_number CHECK (page_number >= 1), 
    CONSTRAINT ck_document_pages_text_characters CHECK (text_characters = char_length(raw_text)), 
    CONSTRAINT ck_document_pages_dimensions CHECK (width_points > 0 AND height_points > 0), 
    CONSTRAINT fk_document_pages_parse_run_id_extraction_runs FOREIGN KEY(parse_run_id, report_id) REFERENCES extraction_runs (id, report_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_document_pages_report_id_reports FOREIGN KEY(report_id) REFERENCES reports (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pages_provenance UNIQUE (id, report_id, parse_run_id, page_number), 
    CONSTRAINT uq_pages_run_number UNIQUE (report_id, parse_run_id, page_number)
);

CREATE INDEX ix_pages_report_number ON document_pages (report_id, page_number);

CREATE INDEX ix_pages_run_status ON document_pages (parse_run_id, status);

CREATE TABLE document_tables (
    document_page_id UUID NOT NULL, 
    report_id UUID NOT NULL, 
    parse_run_id UUID NOT NULL, 
    page_number INTEGER NOT NULL, 
    table_index INTEGER NOT NULL, 
    row_count INTEGER NOT NULL, 
    column_count INTEGER NOT NULL, 
    cells JSONB NOT NULL, 
    bbox JSONB NOT NULL, 
    cell_bboxes JSONB NOT NULL, 
    header_metadata JSONB NOT NULL, 
    extraction_metadata JSONB NOT NULL, 
    content_sha256 VARCHAR(64) NOT NULL, 
    extraction_method VARCHAR(80) NOT NULL, 
    parser_version VARCHAR(80) NOT NULL, 
    validation_state VARCHAR(24) DEFAULT 'needs_review' NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_document_tables PRIMARY KEY (id), 
    CONSTRAINT ck_document_tables_checksum CHECK (content_sha256 ~ '^[0-9a-f]{64}$'), 
    CONSTRAINT ck_document_tables_unverified CHECK (validation_state = 'needs_review'), 
    CONSTRAINT ck_document_tables_shape CHECK (table_index >= 0 AND row_count >= 2 AND column_count >= 2), 
    CONSTRAINT fk_document_tables_document_page_id_document_pages FOREIGN KEY(document_page_id, report_id, parse_run_id, page_number) REFERENCES document_pages (id, report_id, parse_run_id, page_number) ON DELETE RESTRICT, 
    CONSTRAINT uq_tables_page_index UNIQUE (document_page_id, table_index)
);

CREATE INDEX ix_tables_parse_run ON document_tables (parse_run_id);

CREATE INDEX ix_tables_report_page ON document_tables (report_id, page_number);

ALTER TABLE document_chunks ADD COLUMN document_page_id UUID;

ALTER TABLE document_chunks ADD COLUMN source_char_start INTEGER;

ALTER TABLE document_chunks ADD COLUMN source_char_end INTEGER;

ALTER TABLE document_chunks ADD COLUMN source_spans JSONB;

CREATE INDEX ix_chunks_document_page ON document_chunks (document_page_id);

ALTER TABLE document_chunks ADD CONSTRAINT fk_document_chunks_document_page_id_document_pages FOREIGN KEY(document_page_id, report_id, parse_run_id, physical_page_start) REFERENCES document_pages (id, report_id, parse_run_id, page_number) ON DELETE RESTRICT;

ALTER TABLE document_chunks ADD CONSTRAINT ck_document_chunks_page_provenance CHECK (document_page_id IS NULL OR (physical_page_start = physical_page_end AND source_char_start IS NOT NULL AND source_char_end IS NOT NULL AND source_char_start >= 0 AND source_char_end > source_char_start));

CREATE FUNCTION sbi_check_page_chunk() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE page_text text;
    BEGIN
      IF NEW.document_page_id IS NOT NULL THEN
        SELECT ordered_text INTO page_text FROM document_pages WHERE id = NEW.document_page_id;
        IF page_text IS NULL OR NEW.source_char_end > char_length(page_text)
          OR substring(page_text FROM NEW.source_char_start + 1 FOR NEW.source_char_end - NEW.source_char_start) IS DISTINCT FROM NEW.text
          OR encode(sha256(convert_to(NEW.text, 'UTF8')), 'hex') <> NEW.text_sha256 THEN
          RAISE EXCEPTION 'Chunk must be a hash-verified exact slice of its source page' USING ERRCODE = '23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;

CREATE TRIGGER page_text_provenance BEFORE INSERT OR UPDATE ON document_chunks FOR EACH ROW EXECUTE FUNCTION sbi_check_page_chunk();

CREATE FUNCTION sbi_protect_parsed_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'Parsed evidence is immutable; create a new parse run' USING ERRCODE = '23514';
    END $$;

CREATE TRIGGER parsed_immutable BEFORE UPDATE OR DELETE ON document_pages FOR EACH ROW EXECUTE FUNCTION sbi_protect_parsed_evidence();

CREATE TRIGGER parsed_immutable BEFORE UPDATE OR DELETE ON document_tables FOR EACH ROW EXECUTE FUNCTION sbi_protect_parsed_evidence();

CREATE TRIGGER parsed_immutable BEFORE UPDATE OR DELETE ON document_chunks FOR EACH ROW WHEN (OLD.document_page_id IS NOT NULL) EXECUTE FUNCTION sbi_protect_parsed_evidence();

CREATE FUNCTION sbi_check_parsed_page() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM extraction_runs WHERE id = NEW.parse_run_id AND stage = 'parsing')
        OR encode(sha256(convert_to(NEW.raw_text, 'UTF8')), 'hex') <> NEW.raw_text_sha256
        OR encode(sha256(convert_to(NEW.ordered_text, 'UTF8')), 'hex') <> NEW.ordered_text_sha256 THEN
        RAISE EXCEPTION 'Page must cite a parsing run and matching text hashes' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;

CREATE TRIGGER parsed_page_provenance BEFORE INSERT ON document_pages FOR EACH ROW EXECUTE FUNCTION sbi_check_parsed_page();

UPDATE alembic_version SET version_num='53487b8db383' WHERE alembic_version.version_num = 'f0b2edabe086';

-- Running upgrade 53487b8db383 -> 840b86a2302e

ALTER TABLE metric_definitions ADD COLUMN catalogue_version VARCHAR(32);

ALTER TABLE metric_definitions ADD COLUMN category VARCHAR(32);

ALTER TABLE metric_definitions ADD COLUMN evidence_kind VARCHAR(32);

ALTER TABLE metric_definitions ADD COLUMN allowed_units JSONB;

ALTER TABLE metric_definitions ADD COLUMN aliases JSONB;

ALTER TABLE metric_definitions ADD COLUMN normalisation_rule JSONB;

ALTER TABLE metric_definitions ADD COLUMN comparability_warning TEXT;

ALTER TABLE metric_definitions ADD COLUMN score_eligibility VARCHAR(32);

ALTER TABLE metric_definitions ADD COLUMN validation_constraints JSONB;

ALTER TABLE metric_definitions ALTER COLUMN canonical_unit DROP NOT NULL;

CREATE INDEX ix_metrics_catalogue_category ON metric_definitions (catalogue_version, category, metric_code);

ALTER TABLE metric_definitions ADD CONSTRAINT ck_metric_definitions_catalogue_contract CHECK (catalogue_version IS NULL OR (definition_version > 0 AND category IS NOT NULL AND category IN ('climate','energy','targets','water','waste','governance','social','supply_chain','disclosure_quality') AND allowed_units IS NOT NULL AND jsonb_typeof(allowed_units) = 'array' AND aliases IS NOT NULL AND jsonb_typeof(aliases) = 'array' AND normalisation_rule IS NOT NULL AND jsonb_typeof(normalisation_rule) = 'object' AND validation_constraints IS NOT NULL AND jsonb_typeof(validation_constraints) = 'object' AND comparability_warning IS NOT NULL AND btrim(comparability_warning) <> '' AND score_eligibility IS NOT NULL AND score_eligibility IN ('not_eligible','conditional') AND value_type IN ('decimal','integer','boolean','enum','text','object') AND directionality IN ('lower','higher','none') AND evidence_kind IS NOT NULL AND evidence_kind IN ('performance','target','governance','disclosure','programme') AND normalisation_rule_version IS NOT NULL AND validation_rule_version IS NOT NULL));

ALTER TABLE metric_definitions ADD CONSTRAINT ck_metric_definitions_conditional_scoring CHECK (catalogue_version IS NULL OR score_eligibility <> 'conditional' OR (evidence_kind = 'performance' AND value_type IN ('decimal','integer') AND directionality IN ('lower','higher') AND jsonb_array_length(required_comparison_dimensions) > 0));

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Base-year emissions', 'Historical emissions baseline for the identified metric, target and inventory boundary.', 'climate', 'performance', 'absolute', 'tCO2e', CAST('["tCO2e", "kgCO2e", "ktCO2e", "MtCO2e"]' AS JSONB), CAST('["baseline emissions", "emissions in base year"]' AS JSONB), CAST('{"id": "ghg_mass_to_tco2e", "version": "1", "kind": "scale", "description": "Multiply only explicit CO2-equivalent mass units by exact decimal factors. Never convert CO2-only, carbon mass, offsets or avoided emissions into gross GHG emissions.", "factors_to_canonical": {"tCO2e": "1", "kgCO2e": "0.001", "ktCO2e": "1000", "MtCO2e": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'A baseline is historical context, not current achieved performance. Restated and original baselines must not be mixed; the baseline year is not the current reporting year.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "base_year", "baseline_metric_id", "included_scopes", "restatement_basis", "target_reference"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Gross inventory values exclude offsets, avoided emissions and separately reported removals."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "base_year", "baseline_metric_id", "included_scopes", "restatement_basis", "target_reference"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'base_year_emissions', 'base_year_emissions', 'decimal', 'none', '384dfeee-d744-5fdd-9aaa-70908d839c33', 'ghg_mass_to_tco2e@1', 'catalogue:1.0.0:base_year_emissions', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Emissions intensity', 'Reported GHG emissions per explicitly defined activity, output, employee or monetary denominator.', 'climate', 'performance', 'intensity', NULL, CAST('["tCO2e/{denominator_unit}", "kgCO2e/{denominator_unit}", "ktCO2e/{denominator_unit}"]' AS JSONB), CAST('["GHG intensity", "carbon emissions intensity"]' AS JSONB), CAST('{"id": "ghg_intensity_contextual", "version": "1", "kind": "contextual", "description": "Normalise the numerator to tCO2e only after its scope and GWP basis are known. Preserve denominator identity, unit and scale; no currency FX, revenue inflation adjustment or denominator substitution is implicit.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": "tCO2e/{denominator_unit}", "requires_context": ["numerator_metric_id", "denominator_name", "denominator_unit", "denominator_scale", "currency_code_if_monetary", "currency_basis_if_monetary"], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Revenue, production, electricity and headcount intensities cannot be pooled. Currency, price year, denominator scaling, sector and included emissions must match.', 'conditional', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "numerator_metric_id", "denominator_name", "denominator_unit", "denominator_scale", "denominator_value", "currency_code_if_monetary", "currency_basis_if_monetary", "peer_activity"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Denominator value must be greater than zero.", "Unit entries are templates, not interchangeable units; unresolved denominator or scope means not_comparable."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "numerator_metric_id", "denominator_name", "denominator_unit", "denominator_scale", "denominator_value", "currency_code_if_monetary", "currency_basis_if_monetary", "peer_activity"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'emissions_intensity', 'emissions_intensity', 'decimal', 'lower', '93015ef0-bb66-58b1-8702-5738c6e36229', 'ghg_intensity_contextual@1', 'catalogue:1.0.0:emissions_intensity', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Combined Scope 1 and Scope 2 emissions', 'Reported sum of gross Scope 1 plus exactly one explicitly identified Scope 2 method.', 'climate', 'performance', 'absolute', 'tCO2e', CAST('["tCO2e", "kgCO2e", "ktCO2e", "MtCO2e"]' AS JSONB), CAST('["scope 1 and 2 emissions", "combined scope 1+2 emissions"]' AS JSONB), CAST('{"id": "ghg_mass_to_tco2e", "version": "1", "kind": "scale", "description": "Multiply only explicit CO2-equivalent mass units by exact decimal factors. Never convert CO2-only, carbon mass, offsets or avoided emissions into gross GHG emissions.", "factors_to_canonical": {"tCO2e": "1", "kgCO2e": "0.001", "ktCO2e": "1000", "MtCO2e": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Do not sum location- and market-based Scope 2. A combined number without its Scope 2 method is not comparable; no automatic total is derived.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "scope2_method", "included_scopes"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Gross inventory values exclude offsets, avoided emissions and separately reported removals."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "scope2_method", "included_scopes"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'scope_1_2_combined', 'scope_1_2_combined', 'decimal', 'none', 'fe4de578-2071-57a2-be11-f56fe0833558', 'ghg_mass_to_tco2e@1', 'catalogue:1.0.0:scope_1_2_combined', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Scope 1 emissions', 'Direct gross GHG emissions from sources owned or controlled under the stated consolidation basis.', 'climate', 'performance', 'absolute', 'tCO2e', CAST('["tCO2e", "kgCO2e", "ktCO2e", "MtCO2e"]' AS JSONB), CAST('["scope 1 GHG emissions", "direct greenhouse gas emissions"]' AS JSONB), CAST('{"id": "ghg_mass_to_tco2e", "version": "1", "kind": "scale", "description": "Multiply only explicit CO2-equivalent mass units by exact decimal factors. Never convert CO2-only, carbon mass, offsets or avoided emissions into gross GHG emissions.", "factors_to_canonical": {"tCO2e": "1", "kgCO2e": "0.001", "ktCO2e": "1000", "MtCO2e": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Company size, acquisitions, control basis, gas coverage and GWP versions affect totals; gross direct emissions are not offset-adjusted net emissions.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Gross inventory values exclude offsets, avoided emissions and separately reported removals."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'scope_1_emissions', 'scope_1_emissions', 'decimal', 'none', '8bef2924-5553-5f69-985c-8be8e5a06c0f', 'ghg_mass_to_tco2e@1', 'catalogue:1.0.0:scope_1_emissions', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Scope 2 emissions — location-based', 'Gross indirect energy emissions using the stated location-based method.', 'climate', 'performance', 'absolute', 'tCO2e', CAST('["tCO2e", "kgCO2e", "ktCO2e", "MtCO2e"]' AS JSONB), CAST('["location-based scope 2 emissions", "scope 2 location based"]' AS JSONB), CAST('{"id": "ghg_mass_to_tco2e", "version": "1", "kind": "scale", "description": "Multiply only explicit CO2-equivalent mass units by exact decimal factors. Never convert CO2-only, carbon mass, offsets or avoided emissions into gross GHG emissions.", "factors_to_canonical": {"tCO2e": "1", "kgCO2e": "0.001", "ktCO2e": "1000", "MtCO2e": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Never pool with market-based Scope 2 or add both methods together. Grid geography and included purchased energy types differ.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "scope2_method", "purchased_energy_types"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "scope2_method must equal location_based."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "scope2_method", "purchased_energy_types"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'scope_2_location_based', 'scope_2_location_based', 'decimal', 'none', '4664e5d4-f3ff-5c73-a1b2-02df84219fc8', 'ghg_mass_to_tco2e@1', 'catalogue:1.0.0:scope_2_location_based', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Scope 2 emissions — market-based', 'Gross indirect energy emissions using the stated market-based method and eligible contractual instruments.', 'climate', 'performance', 'absolute', 'tCO2e', CAST('["tCO2e", "kgCO2e", "ktCO2e", "MtCO2e"]' AS JSONB), CAST('["market-based scope 2 emissions", "scope 2 market based"]' AS JSONB), CAST('{"id": "ghg_mass_to_tco2e", "version": "1", "kind": "scale", "description": "Multiply only explicit CO2-equivalent mass units by exact decimal factors. Never convert CO2-only, carbon mass, offsets or avoided emissions into gross GHG emissions.", "factors_to_canonical": {"tCO2e": "1", "kgCO2e": "0.001", "ktCO2e": "1000", "MtCO2e": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Never pool with location-based Scope 2 or treat contractual reductions as identical to physical grid reductions. Instrument quality and residual mixes matter.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "scope2_method", "purchased_energy_types", "contractual_instrument_basis"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "scope2_method must equal market_based."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "scope2_method", "purchased_energy_types", "contractual_instrument_basis"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'scope_2_market_based', 'scope_2_market_based', 'decimal', 'none', 'cd3ba742-a79b-575e-baf1-1580ce33bb5a', 'ghg_mass_to_tco2e@1', 'catalogue:1.0.0:scope_2_market_based', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Scope 3 emissions', 'Reported gross value-chain GHG emissions for the explicit set of included categories.', 'climate', 'performance', 'absolute', 'tCO2e', CAST('["tCO2e", "kgCO2e", "ktCO2e", "MtCO2e"]' AS JSONB), CAST('["scope 3 GHG emissions", "value chain emissions"]' AS JSONB), CAST('{"id": "ghg_mass_to_tco2e", "version": "1", "kind": "scale", "description": "Multiply only explicit CO2-equivalent mass units by exact decimal factors. Never convert CO2-only, carbon mass, offsets or avoided emissions into gross GHG emissions.", "factors_to_canonical": {"tCO2e": "1", "kgCO2e": "0.001", "ktCO2e": "1000", "MtCO2e": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Different category coverage, estimation methods and financed-emissions boundaries make totals non-comparable; do not imply coverage of all 15 categories.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "scope3_categories", "category_methodologies", "financed_emissions_boundary"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Gross inventory values exclude offsets, avoided emissions and separately reported removals."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "scope3_categories", "category_methodologies", "financed_emissions_boundary"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'scope_3_emissions', 'scope_3_emissions', 'decimal', 'none', '929cc106-3223-5ac1-87f1-037a5e29fd16', 'ghg_mass_to_tco2e@1', 'catalogue:1.0.0:scope_3_emissions', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Total GHG emissions as reported', 'Company-labelled GHG total with its original included scopes and reconciliation retained.', 'climate', 'performance', 'absolute', 'tCO2e', CAST('["tCO2e", "kgCO2e", "ktCO2e", "MtCO2e"]' AS JSONB), CAST('["total greenhouse gas emissions", "total carbon footprint"]' AS JSONB), CAST('{"id": "ghg_mass_to_tco2e", "version": "1", "kind": "scale", "description": "Multiply only explicit CO2-equivalent mass units by exact decimal factors. Never convert CO2-only, carbon mass, offsets or avoided emissions into gross GHG emissions.", "factors_to_canonical": {"tCO2e": "1", "kgCO2e": "0.001", "ktCO2e": "1000", "MtCO2e": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'The word total is not a consistent boundary. May omit Scope 3 or include netting; never equate this generic total with a defined Scope 1+2+3 inventory.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "included_scopes", "scope2_method", "scope3_categories", "total_reconciliation"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Gross inventory values exclude offsets, avoided emissions and separately reported removals."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "included_scopes", "scope2_method", "scope3_categories", "total_reconciliation"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'total_ghg_reported', 'total_ghg_reported', 'decimal', 'none', '10dd4308-e820-5d29-9540-1dd2f5a2f24d', 'ghg_mass_to_tco2e@1', 'catalogue:1.0.0:total_ghg_reported', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Year-on-year emissions change', 'Percentage change in the same emissions measure relative to a comparable immediately preceding annual period.', 'climate', 'performance', 'percent_change', '%', CAST('["%", "fraction"]' AS JSONB), CAST('["year over year GHG change", "annual emissions reduction percent"]' AS JSONB), CAST('{"id": "yoy_percent_change", "version": "1", "kind": "contextual", "description": "Canonical sign is (current - prior) / prior * 100. Use reported change only with stated sign convention; reverse a stated reduction percentage explicitly. Do not treat percentage points as percent change or derive from incompatible periods.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": ["prior_year", "prior_emissions", "comparison_metric_id", "sign_convention", "restatement_basis"], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Prior emissions must be positive. Restatements, boundary changes, acquisitions, period length and absolute-versus-intensity definitions can invalidate the trend.', 'conditional', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "-100", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "prior_year", "prior_emissions", "comparison_metric_id", "sign_convention", "restatement_basis"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Prior year must immediately precede the current reporting year and prior value must be greater than zero.", "Negative means decrease; positive means increase. An increase above 100 percent is allowed.", "The -100 percent floor applies only to comparable nonnegative gross inventories."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "ghg_inventory_standard", "gwp_basis", "gases_included", "gross_or_net", "biogenic_co2_treatment", "prior_year", "prior_emissions", "comparison_metric_id", "sign_convention", "restatement_basis"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'yoy_emissions_change', 'yoy_emissions_change', 'decimal', 'lower', '79b8a8d5-5b80-5f19-b364-6db6193e29a1', 'yoy_percent_change@1', 'catalogue:1.0.0:yoy_emissions_change', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Electricity consumption', 'Electricity consumed by the stated operations, with purchased and self-generated coverage identified.', 'energy', 'performance', 'absolute', 'GJ', CAST('["GJ", "MJ", "TJ", "PJ", "kWh", "MWh", "GWh"]' AS JSONB), CAST('["electricity used", "total electricity consumed"]' AS JSONB), CAST('{"id": "energy_to_gj", "version": "1", "kind": "scale", "description": "Convert explicit energy quantities to GJ using exact decimal factors. Power units (kW/MW), primary-versus-final energy, heating-value bases and sold-versus-consumed energy are not interchangeable.", "factors_to_canonical": {"GJ": "1", "MJ": "0.001", "TJ": "1000", "PJ": "1000000", "kWh": "0.0036", "MWh": "3.6", "GWh": "3600"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Consumed electricity differs from purchased, generated or exported electricity. Do not treat this subset as total energy.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "energy_basis", "heating_value_basis", "included_energy_carriers", "self_generation_and_exports"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "energy_basis", "heating_value_basis", "included_energy_carriers", "self_generation_and_exports"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'electricity_consumption', 'electricity_consumption', 'decimal', 'none', '400609e1-9acb-5f91-a4fd-b82bc6e44a70', 'energy_to_gj@1', 'catalogue:1.0.0:electricity_consumption', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Renewable electricity percentage', 'Renewable electricity consumed divided by total electricity consumed for the same boundary.', 'energy', 'performance', 'share', '%', CAST('["%", "fraction"]' AS JSONB), CAST('["renewable electricity share", "percentage renewable electricity"]' AS JSONB), CAST('{"id": "explicit_share_to_percent", "version": "1", "kind": "scale", "description": "Convert a share explicitly labelled percent or fraction to percent. A decimal such as 0.5 is not assumed to be a fraction. Percentage-point changes are not percentage levels.", "factors_to_canonical": {"%": "1", "fraction": "100"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Electricity is only a subset of energy. Physical supply, certificates and contractual procurement methods require separate or harmonised comparison groups.', 'conditional', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": "100", "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "renewable_electricity_numerator", "total_electricity_denominator", "renewable_claim_method"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Numerator and denominator must cover the same period/boundary and denominator must be greater than zero."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "renewable_electricity_numerator", "total_electricity_denominator", "renewable_claim_method"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'renewable_electricity_percent', 'renewable_electricity_percent', 'decimal', 'higher', '157cc266-7ee7-5f34-8a63-1d0d9fcdf150', 'explicit_share_to_percent@1', 'catalogue:1.0.0:renewable_electricity_percent', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Renewable energy percentage', 'Renewable energy consumed divided by total energy consumed on a consistent energy basis.', 'energy', 'performance', 'share', '%', CAST('["%", "fraction"]' AS JSONB), CAST('["renewable energy share", "percentage renewable energy"]' AS JSONB), CAST('{"id": "explicit_share_to_percent", "version": "1", "kind": "scale", "description": "Convert a share explicitly labelled percent or fraction to percent. A decimal such as 0.5 is not assumed to be a fraction. Percentage-point changes are not percentage levels.", "factors_to_canonical": {"%": "1", "fraction": "100"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Do not substitute renewable electricity share. Fuel sustainability definitions, heating values and energy carrier coverage affect comparability.', 'conditional', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": "100", "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "renewable_energy_numerator", "total_energy_denominator", "renewable_definition", "energy_basis"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Numerator and denominator must cover the same period/boundary and denominator must be greater than zero."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "renewable_energy_numerator", "total_energy_denominator", "renewable_definition", "energy_basis"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'renewable_energy_percent', 'renewable_energy_percent', 'decimal', 'higher', '3d926004-5d83-5891-99c5-b64ed0a7db42', 'explicit_share_to_percent@1', 'catalogue:1.0.0:renewable_energy_percent', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Total energy consumption', 'Energy consumed within the stated organisational boundary, across explicitly included energy carriers.', 'energy', 'performance', 'absolute', 'GJ', CAST('["GJ", "MJ", "TJ", "PJ", "kWh", "MWh", "GWh"]' AS JSONB), CAST('["total energy use", "energy consumed within the organisation"]' AS JSONB), CAST('{"id": "energy_to_gj", "version": "1", "kind": "scale", "description": "Convert explicit energy quantities to GJ using exact decimal factors. Power units (kW/MW), primary-versus-final energy, heating-value bases and sold-versus-consumed energy are not interchangeable.", "factors_to_canonical": {"GJ": "1", "MJ": "0.001", "TJ": "1000", "PJ": "1000000", "kWh": "0.0036", "MWh": "3.6", "GWh": "3600"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Do not combine primary/final energy, heating-value conventions or energy sold with energy consumed. Absolute totals are size-dependent.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "energy_basis", "heating_value_basis", "included_energy_carriers", "self_generation_and_exports"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "energy_basis", "heating_value_basis", "included_energy_carriers", "self_generation_and_exports"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'total_energy_consumption', 'total_energy_consumption', 'decimal', 'none', 'b04fe958-176f-5749-840f-802788b325a8', 'energy_to_gj@1', 'catalogue:1.0.0:total_energy_consumption', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Carbon-neutral target year', 'Target year for the company''s explicitly defined carbon-neutrality commitment; not an achieved result.', 'targets', 'target', 'absolute', 'year', CAST('["year"]' AS JSONB), CAST('["carbon neutrality target date", "carbon neutral by"]' AS JSONB), CAST('{"id": "target_year_identity", "version": "1", "kind": "identity", "description": "Retain an explicitly stated four-digit target calendar year. No inferred year from phrases such as soon, future or carbon neutral; retain claim wording separately.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Net zero and carbon neutrality are not interchangeable. Target scope, gases, residual emissions, offsets/removals and validation differ; earlier does not automatically rank better.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "1900", "maximum": "2200", "integer_only": true, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "target_scope", "included_gases", "target_definition", "offsets_and_removals_role", "target_status"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Store under targets, never as achieved performance.", "A past target date is retained with status evidence; do not silently roll it forward."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "target_scope", "included_gases", "target_definition", "offsets_and_removals_role", "target_status"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'carbon_neutral_target_year', 'carbon_neutral_target_year', 'integer', 'none', '0dc834a3-2415-50be-9dde-2a7e8c04b73a', 'target_year_identity@1', 'catalogue:1.0.0:carbon_neutral_target_year', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Interim emissions target', 'A time-bound interim GHG target with baseline, amount, metric basis and scope retained together.', 'targets', 'target', 'categorical', NULL, CAST('[]' AS JSONB), CAST('["near-term emissions target", "interim GHG reduction target"]' AS JSONB), CAST('{"id": "interim_target_structured", "version": "1", "kind": "structured", "description": "Retain a structured target: absolute or intensity basis, stated amount/unit, target and baseline years, scope and status. Numeric/unit normalisation is deferred until all target dimensions are explicit; no single scalar unit exists.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'A 50 percent intensity target and a 50 percent absolute reduction target are not equivalent. Targets are commitments, not achieved reductions.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": {"type": "object", "additionalProperties": false, "properties": {"target_year": {"type": "integer", "minimum": 1900, "maximum": 2200}, "baseline_year": {"type": ["integer", "null"], "minimum": 1900, "maximum": 2200}, "target_basis": {"enum": ["absolute", "intensity"]}, "amount": {"type": "string", "description": "Exact raw decimal string, not a float."}, "unit": {"type": "string", "minLength": 1}, "scope": {"type": "string", "minLength": 1}, "status": {"type": "string", "minLength": 1}}, "required": ["target_year", "baseline_year", "target_basis", "amount", "unit", "scope", "status"]}, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "target_year", "baseline_year", "target_basis", "target_scope", "baseline_value", "target_status"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Baseline year must not exceed target year when present.", "Percent reductions must be between 0 and 100; an absolute target amount must be nonnegative.", "Intensity targets additionally require denominator identity, unit and scale.", "Store under targets; no observation or ranked scalar is created."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "target_year", "baseline_year", "target_basis", "target_scope", "baseline_value", "target_status"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'interim_emissions_target', 'interim_emissions_target', 'object', 'none', '2b8e28d4-9155-5a9d-a314-b12d97b8856a', 'interim_target_structured@1', 'catalogue:1.0.0:interim_emissions_target', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Net-zero target year', 'Target year for an explicitly defined net-zero commitment; not an achieved result.', 'targets', 'target', 'absolute', 'year', CAST('["year"]' AS JSONB), CAST('["net zero by", "net-zero ambition year"]' AS JSONB), CAST('{"id": "target_year_identity", "version": "1", "kind": "identity", "description": "Retain an explicitly stated four-digit target calendar year. No inferred year from phrases such as soon, future or carbon neutral; retain claim wording separately.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Net zero and carbon neutrality are not interchangeable. Target scope, gases, residual emissions, offsets/removals and validation differ; earlier does not automatically rank better.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "1900", "maximum": "2200", "integer_only": true, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "target_scope", "included_gases", "target_definition", "offsets_and_removals_role", "target_status"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Store under targets, never as achieved performance.", "A past target date is retained with status evidence; do not silently roll it forward."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "target_scope", "included_gases", "target_definition", "offsets_and_removals_role", "target_status"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'net_zero_target_year', 'net_zero_target_year', 'integer', 'none', '289c14e5-2ee8-5400-a481-a0b365e411dc', 'target_year_identity@1', 'catalogue:1.0.0:net_zero_target_year', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'SBTi status', 'Reported science-based-target commitment or validation status at a specific date, including near-term/net-zero applicability.', 'targets', 'target', 'categorical', NULL, CAST('[]' AS JSONB), CAST('["science based targets initiative status", "SBTi commitment or validation"]' AS JSONB), CAST('{"id": "sbti_status_map", "version": "1", "kind": "enum_map", "description": "Map only explicit reported labels to the internal non-ordinal status vocabulary. Preserve the original status label, source/date and whether the claim was checked against SBTi. Unrecognised labels remain other_reported_status with raw text.", "factors_to_canonical": {}, "value_aliases": {"Committed": "committed", "Commitment to Set Targets": "committed", "Targets Set": "validated_targets", "Validated Targets": "validated_targets", "Commitment Removed": "commitment_removed"}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Commitment is not validation, and target validation is not achieved performance. SBTi labels and standard versions evolve; retain as-of date, target type and raw label.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": ["committed", "validated_targets", "commitment_removed", "other_reported_status"], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "status_as_of", "raw_status_label", "status_source", "target_type", "sbti_standard_version"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "This internal vocabulary is not an ordinal score or a claim to reproduce every official SBTi status.", "Company-reported validation is not independently verified unless the status source documents that check."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "status_as_of", "raw_status_label", "status_source", "target_type", "sbti_standard_version"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'sbti_status', 'sbti_status', 'enum', 'none', '84e20386-0b95-5ea2-b457-c09b55bc2e92', 'sbti_status_map@1', 'catalogue:1.0.0:sbti_status', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Water consumption', 'Water consumed under the report''s stated definition, including the treatment of storage changes.', 'water', 'performance', 'absolute', 'm3', CAST('["m3", "L", "kL", "ML", "GL"]' AS JSONB), CAST('["total water consumed", "consumptive water use"]' AS JSONB), CAST('{"id": "water_to_m3", "version": "1", "kind": "scale", "description": "Convert explicit water volume to cubic metres. An unspecified gallon is ambiguous; no density-based mass conversion, netting, or withdrawal/consumption/discharge substitution.", "factors_to_canonical": {"m3": "1", "L": "0.001", "kL": "1", "ML": "1000", "GL": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Consumption is not gross withdrawal. Do not automatically compute withdrawal minus discharge when periods, storage or boundaries differ.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "water_sources_or_destinations", "freshwater_definition", "water_stress_boundary", "basin_coverage", "storage_change_treatment"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "water_sources_or_destinations", "freshwater_definition", "water_stress_boundary", "basin_coverage", "storage_change_treatment"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'water_consumption', 'water_consumption', 'decimal', 'none', '05f4bbca-455c-57c0-84a8-ba6140bf8223', 'water_to_m3@1', 'catalogue:1.0.0:water_consumption', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Water discharge', 'Water discharged to explicitly identified destinations during the reporting period.', 'water', 'performance', 'absolute', 'm3', CAST('["m3", "L", "kL", "ML", "GL"]' AS JSONB), CAST('["total water discharged", "water effluent volume"]' AS JSONB), CAST('{"id": "water_to_m3", "version": "1", "kind": "scale", "description": "Convert explicit water volume to cubic metres. An unspecified gallon is ambiguous; no density-based mass conversion, netting, or withdrawal/consumption/discharge substitution.", "factors_to_canonical": {"m3": "1", "L": "0.001", "kL": "1", "ML": "1000", "GL": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Discharge volume says nothing alone about water quality or receiving-basin impact. Withdrawal, consumption and discharge cannot be pooled.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "water_sources_or_destinations", "freshwater_definition", "water_stress_boundary", "basin_coverage", "storage_change_treatment"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "water_sources_or_destinations", "freshwater_definition", "water_stress_boundary", "basin_coverage", "storage_change_treatment"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'water_discharge', 'water_discharge', 'decimal', 'none', '549b0688-9866-5f42-a0b4-b28c20abf550', 'water_to_m3@1', 'catalogue:1.0.0:water_discharge', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Water withdrawal', 'Water drawn into the organisation from all explicitly included sources during the reporting period.', 'water', 'performance', 'absolute', 'm3', CAST('["m3", "L", "kL", "ML", "GL"]' AS JSONB), CAST('["total water withdrawal", "water abstracted"]' AS JSONB), CAST('{"id": "water_to_m3", "version": "1", "kind": "scale", "description": "Convert explicit water volume to cubic metres. An unspecified gallon is ambiguous; no density-based mass conversion, netting, or withdrawal/consumption/discharge substitution.", "factors_to_canonical": {"m3": "1", "L": "0.001", "kL": "1", "ML": "1000", "GL": "1000000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Withdrawal is not consumption or discharge. Compare sources, freshwater coverage and water-stressed basin exposure; company-wide volume alone is not water impact.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "water_sources_or_destinations", "freshwater_definition", "water_stress_boundary", "basin_coverage", "storage_change_treatment"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "water_sources_or_destinations", "freshwater_definition", "water_stress_boundary", "basin_coverage", "storage_change_treatment"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'water_withdrawal', 'water_withdrawal', 'decimal', 'none', '7a4b19bd-b525-5af9-8ef2-c09be8a80469', 'water_to_m3@1', 'catalogue:1.0.0:water_withdrawal', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Hazardous waste generated', 'Mass of waste generated and classified hazardous under the explicitly identified legal or reporting definition.', 'waste', 'performance', 'absolute', 't', CAST('["t", "kg", "kt"]' AS JSONB), CAST('["hazardous waste generation", "total hazardous waste"]' AS JSONB), CAST('{"id": "waste_mass_to_t", "version": "1", "kind": "scale", "description": "Convert explicit metric mass to tonnes. An unspecified ton, short ton, long ton, volume or percentage requires review; do not infer metric tonnes.", "factors_to_canonical": {"t": "1", "kg": "0.001", "kt": "1000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Hazardous definitions vary by jurisdiction. Compare the same classification and boundary; do not assume every report uses the same hazard criteria.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "waste_boundary", "waste_classification", "jurisdiction", "generated_or_managed"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "waste_boundary", "waste_classification", "jurisdiction", "generated_or_managed"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'hazardous_waste', 'hazardous_waste', 'decimal', 'none', '0c2e3753-6dfa-5746-8433-f8e01a5a5649', 'waste_mass_to_t@1', 'catalogue:1.0.0:hazardous_waste', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Waste recycled or diverted percentage', 'Share of the stated waste denominator recycled or diverted, with the exact recovery routes retained.', 'waste', 'performance', 'share', '%', CAST('["%", "fraction"]' AS JSONB), CAST('["waste recycling rate", "waste diversion rate"]' AS JSONB), CAST('{"id": "explicit_share_to_percent", "version": "1", "kind": "scale", "description": "Convert a share explicitly labelled percent or fraction to percent. A decimal such as 0.5 is not assumed to be a fraction. Percentage-point changes are not percentage levels.", "factors_to_canonical": {"%": "1", "fraction": "100"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Recycling, diversion from disposal and diversion from landfill are not synonyms. Incineration with energy recovery may count in diversion but not recycling; compare identical route definitions only.', 'conditional', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": "100", "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "recovery_route_definition", "included_treatment_routes", "waste_denominator", "generated_or_managed"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Denominator must be positive and numerator must be a subset of the same waste boundary.", "The canonical ID is a family; recycling and diversion must use separate comparison groups."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "recovery_route_definition", "included_treatment_routes", "waste_denominator", "generated_or_managed"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'recycled_or_diverted_percent', 'recycled_or_diverted_percent', 'decimal', 'higher', '2e66f039-6aa8-56aa-b9be-e66bfb5d1ee3', 'explicit_share_to_percent@1', 'catalogue:1.0.0:recycled_or_diverted_percent', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Total waste generated', 'Total mass of waste generated within the disclosed boundary, not merely waste disposed.', 'waste', 'performance', 'absolute', 't', CAST('["t", "kg", "kt"]' AS JSONB), CAST('["total waste generated", "waste generation"]' AS JSONB), CAST('{"id": "waste_mass_to_t", "version": "1", "kind": "scale", "description": "Convert explicit metric mass to tonnes. An unspecified ton, short ton, long ton, volume or percentage requires review; do not infer metric tonnes.", "factors_to_canonical": {"t": "1", "kg": "0.001", "kt": "1000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Generation, disposal and waste managed for customers are different quantities. Hazardous classifications and construction/operational coverage differ.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "waste_boundary", "waste_classification", "jurisdiction", "generated_or_managed"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "waste_boundary", "waste_classification", "jurisdiction", "generated_or_managed"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'total_waste', 'total_waste', 'decimal', 'none', '7e2edf81-a24a-5159-a0bd-65f76d3d1f61', 'waste_mass_to_t@1', 'catalogue:1.0.0:total_waste', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Assurance status', 'External assurance status and level for the specified report or metric subset.', 'governance', 'governance', 'categorical', NULL, CAST('[]' AS JSONB), CAST('["external assurance level", "independent sustainability assurance"]' AS JSONB), CAST('{"id": "assurance_level_map", "version": "1", "kind": "enum_map", "description": "Classify explicit assurance opinion wording and retain covered metrics, period, provider, standard and opinion. Do not promote limited assurance to reasonable assurance.", "factors_to_canonical": {}, "value_aliases": {"limited assurance": "limited", "reasonable assurance": "reasonable", "mixed levels": "mixed", "explicitly not assured": "explicitly_not_assured"}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Assurance of selected indicators is not assurance of the whole report. Scope, level, provider independence and qualifications matter; no simple ordinal ranking is assigned.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": ["limited", "reasonable", "mixed", "explicitly_not_assured", "other_reported_level"], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "assurance_scope", "assurance_level", "assurance_provider", "assurance_standard", "assurance_opinion"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Unknown or unstated level cannot be mapped to reasonable or limited.", "An assurance report must cover the relevant period and measures."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "assurance_scope", "assurance_level", "assurance_provider", "assurance_standard", "assurance_opinion"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'assurance_status', 'assurance_status', 'enum', 'none', '6946d13d-dc0e-5070-8923-450acaf4cb89', 'assurance_level_map@1', 'catalogue:1.0.0:assurance_status', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Board sustainability oversight', 'Explicitly documented board or board-committee accountability for sustainability oversight.', 'governance', 'governance', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["board ESG oversight", "board sustainability responsibility"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Committee existence alone does not prove effective oversight or sustainability outcomes; remit, reporting cadence and authority differ.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "oversight_body", "oversight_remit"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "True requires an explicit board-level remit; generic management responsibility is insufficient."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "oversight_body", "oversight_remit"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'board_sustainability_oversight', 'board_sustainability_oversight', 'boolean', 'none', '48055f04-8d04-5895-83ef-8214302e358c', 'explicit_boolean@1', 'catalogue:1.0.0:board_sustainability_oversight', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Climate-linked remuneration', 'Explicit presence of climate-related criteria in executive remuneration arrangements.', 'governance', 'governance', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["climate linked executive pay", "climate incentive remuneration"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'A binary link omits incentive weight, measure quality and actual payout. Generic ESG pay criteria are not necessarily climate-linked.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "covered_executives", "incentive_period", "climate_measure", "incentive_weight"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "True requires a climate-specific measure; do not infer from generic ESG terminology."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "covered_executives", "incentive_period", "climate_measure", "incentive_weight"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'climate_linked_remuneration', 'climate_linked_remuneration', 'boolean', 'none', '4adf91aa-9811-5515-bce7-a562f31386e5', 'explicit_boolean@1', 'catalogue:1.0.0:climate_linked_remuneration', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Executive sustainability owner', 'Explicitly identified executive role accountable for sustainability, distinct from board oversight.', 'governance', 'governance', 'categorical', NULL, CAST('[]' AS JSONB), CAST('["executive ESG accountability", "chief sustainability officer responsibility"]' AS JSONB), CAST('{"id": "executive_role_identity", "version": "1", "kind": "identity", "description": "Retain the explicitly named executive role or accountable office as text; trim surrounding whitespace only. Preserve raw wording and do not infer authority from a title.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Job titles, seniority, remit and accountability differ. A named sustainability officer is not evidence of effective execution and is not an ordinal metric.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "executive_role", "responsibility_remit"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Non-null text must be nonblank and supported by a role/accountability excerpt.", "Do not store private contact details or infer a named individual where only an office is disclosed."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "executive_role", "responsibility_remit"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'executive_sustainability_owner', 'executive_sustainability_owner', 'text', 'none', '4b016080-097d-5c72-8841-073b4bb29f4f', 'executive_role_identity@1', 'catalogue:1.0.0:executive_sustainability_owner', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'ISSB disclosure status', 'Reported reference, alignment claim or explicit compliance statement for identified ISSB standards.', 'governance', 'governance', 'categorical', NULL, CAST('[]' AS JSONB), CAST('["ISSB reporting", "IFRS S1 S2 disclosure"]' AS JSONB), CAST('{"id": "issb_disclosure_map", "version": "1", "kind": "enum_map", "description": "Map explicit disclosure statements only; retain raw claim and framework coverage. Do not infer alignment from keywords or independently certify compliance.", "factors_to_canonical": {}, "value_aliases": {"ISSB referenced": "reference_only", "partial IFRS sustainability disclosure": "partial_disclosure", "ISSB aligned": "claimed_alignment", "explicit IFRS S1 and S2 compliance statement": "explicit_compliance_statement"}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Mentioning ISSB or IFRS S2 does not establish compliance with IFRS S1 and S2. Preserve standard/version, jurisdiction, transition relief and exact claim.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": ["reference_only", "partial_disclosure", "claimed_alignment", "explicit_compliance_statement"], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "framework_version", "disclosure_extent", "claim_basis", "jurisdiction"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Absence is null/not_reported after documented review, not an invented non-compliance finding."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "framework_version", "disclosure_extent", "claim_basis", "jurisdiction"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'issb_disclosure', 'issb_disclosure', 'enum', 'none', 'e51b57d2-d8f1-512b-b7ca-9f21644e1381', 'issb_disclosure_map@1', 'catalogue:1.0.0:issb_disclosure', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'TCFD disclosure status', 'Reported use or claimed alignment with TCFD recommendations, retaining the exact extent of disclosure.', 'governance', 'governance', 'categorical', NULL, CAST('[]' AS JSONB), CAST('["TCFD reporting", "TCFD alignment disclosure"]' AS JSONB), CAST('{"id": "tcfd_disclosure_map", "version": "1", "kind": "enum_map", "description": "Map explicit disclosure statements only; retain raw claim and framework coverage. Do not infer alignment from keywords or independently certify compliance.", "factors_to_canonical": {}, "value_aliases": {"TCFD referenced": "reference_only", "partial TCFD disclosure": "partial_disclosure", "TCFD aligned": "claimed_alignment"}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Mentioning TCFD is not full alignment, assurance or regulatory compliance. Framework reference and substantive disclosure must remain distinct.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": ["reference_only", "partial_disclosure", "claimed_alignment", "explicitly_not_aligned"], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "framework_version", "disclosure_extent", "claim_basis", "jurisdiction"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Absence is null/not_reported after documented review, not an invented non-compliance finding."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "framework_version", "disclosure_extent", "claim_basis", "jurisdiction"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'tcfd_disclosure', 'tcfd_disclosure', 'enum', 'none', '9d846dae-8d83-5465-af10-a5d84cfb9e3f', 'tcfd_disclosure_map@1', 'catalogue:1.0.0:tcfd_disclosure', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Employees', 'Employee headcount for an explicitly stated date or annual averaging basis.', 'social', 'performance', 'absolute', 'persons', CAST('["persons", "thousand_persons"]' AS JSONB), CAST('["employee headcount", "number of employees"]' AS JSONB), CAST('{"id": "headcount_to_persons", "version": "1", "kind": "scale", "description": "Convert explicitly stated headcount to persons. FTE and contractor counts are not headcount units; no implicit conversion or rounding to manufacture an integer.", "factors_to_canonical": {"persons": "1", "thousand_persons": "1000"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Year-end headcount, average headcount, FTE and workers including contractors differ. More employees is not inherently better sustainability performance.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": true, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "headcount_basis", "reference_date_or_averaging_period", "worker_population"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Normalised headcount must be an integer; preserve rounding qualifiers on scaled reported values.", "FTE-only figures require a different definition, not relabelling as persons."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "headcount_basis", "reference_date_or_averaging_period", "worker_population"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'employees', 'employees', 'integer', 'none', 'e80db8f2-a3c1-5c64-b7ab-98a1e9e3a232', 'headcount_to_persons@1', 'catalogue:1.0.0:employees', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Work-related injury rate', 'Reported work-related injury incidence rate with injury definition, population and hours basis retained.', 'social', 'performance', 'rate', 'cases/1000000_hours', CAST('["cases/1000000_hours", "cases/200000_hours"]' AS JSONB), CAST('["recordable injury rate", "lost time injury frequency rate", "TRIR", "LTIFR"]' AS JSONB), CAST('{"id": "injury_rate_per_million_hours", "version": "1", "kind": "scale", "description": "Rescale an explicitly defined injury-rate denominator to one million hours. Retain rate type and covered population; never convert TRIR into LTIFR or employee-only into all-worker rates.", "factors_to_canonical": {"cases/1000000_hours": "1", "cases/200000_hours": "5"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Recordable, lost-time, high-consequence and fatal-injury measures are different metrics. Jurisdiction, reporting incentives and contractor coverage affect comparisons.', 'conditional', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "injury_rate_type", "injury_definition", "worker_population", "hours_worked", "rate_denominator_hours", "jurisdiction"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Hours worked must be positive; base must explicitly equal 200000 or 1000000 hours.", "Aliases are retrieval clues only: recordable and lost-time rates remain separate comparison groups."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "injury_rate_type", "injury_definition", "worker_population", "hours_worked", "rate_denominator_hours", "jurisdiction"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'injury_rate', 'injury_rate', 'decimal', 'lower', '2c9cb8a8-c2b5-5251-9e31-9041f1b50ff5', 'injury_rate_per_million_hours@1', 'catalogue:1.0.0:injury_rate', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Women in management percentage', 'Reported proportion of women within the company''s explicitly defined management population.', 'social', 'performance', 'share', '%', CAST('["%", "fraction"]' AS JSONB), CAST('["female managers percentage", "women in leadership share"]' AS JSONB), CAST('{"id": "explicit_share_to_percent", "version": "1", "kind": "scale", "description": "Convert a share explicitly labelled percent or fraction to percent. A decimal such as 0.5 is not assumed to be a fraction. Percentage-point changes are not percentage levels.", "factors_to_canonical": {"%": "1", "fraction": "100"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Population, management levels, geography, self-identification and missing gender data differ. This descriptive composition measure has no universal higher-is-better direction or automatic ranking.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": "100", "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "management_level_definition", "population_definition", "gender_data_collection_basis"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Denominator must be positive; retain undisclosed/other gender handling and collection method.", "Do not infer counts, gender identities or workforce coverage from the percentage alone."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "management_level_definition", "population_definition", "gender_data_collection_basis"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'women_management_percent', 'women_management_percent', 'decimal', 'none', '37c609cf-256c-5adf-a03a-2175382578ba', 'explicit_share_to_percent@1', 'catalogue:1.0.0:women_management_percent', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Women in workforce percentage', 'Reported proportion of the explicitly defined employee/workforce population identifying as women.', 'social', 'performance', 'share', '%', CAST('["%", "fraction"]' AS JSONB), CAST('["female employees percentage", "women in workforce share"]' AS JSONB), CAST('{"id": "explicit_share_to_percent", "version": "1", "kind": "scale", "description": "Convert a share explicitly labelled percent or fraction to percent. A decimal such as 0.5 is not assumed to be a fraction. Percentage-point changes are not percentage levels.", "factors_to_canonical": {"%": "1", "fraction": "100"}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Population, management levels, geography, self-identification and missing gender data differ. This descriptive composition measure has no universal higher-is-better direction or automatic ranking.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": true, "minimum": "0", "maximum": "100", "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "population_definition", "gender_data_collection_basis"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Denominator must be positive; retain undisclosed/other gender handling and collection method.", "Do not infer counts, gender identities or workforce coverage from the percentage alone."]}' AS JSONB), CAST('["reporting_year", "period_start", "period_end", "organisational_boundary", "consolidation_basis", "coverage_description", "methodology_version", "population_definition", "gender_data_collection_basis"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'women_percent', 'women_percent', 'decimal', 'none', '14039724-13a2-521c-80dd-7f6c867ff823', 'explicit_share_to_percent@1', 'catalogue:1.0.0:women_percent', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Responsible sourcing policy', 'Explicitly published or described responsible-sourcing policy applying to the stated suppliers or materials.', 'supply_chain', 'programme', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["sustainable sourcing policy", "responsible procurement policy"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'A policy is not audited compliance or demonstrated outcomes. Coverage, issue scope, enforcement and exceptions differ.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "policy_scope", "materials_or_suppliers_covered", "enforcement_basis"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "True requires substantive policy/programme evidence, not only an aspirational slogan.", "Targets or supplier code documents do not by themselves establish achieved emissions performance."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "policy_scope", "materials_or_suppliers_covered", "enforcement_basis"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'responsible_sourcing_policy', 'responsible_sourcing_policy', 'boolean', 'none', '05ede88f-41dc-53bd-b2f0-2ac14d620cdc', 'explicit_boolean@1', 'catalogue:1.0.0:responsible_sourcing_policy', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Scope 3 supplier engagement', 'Explicit engagement of suppliers on identified Scope 3 categories, not a numeric emissions outcome.', 'supply_chain', 'programme', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["scope 3 supplier engagement", "value chain supplier climate engagement"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Generic procurement engagement is not necessarily Scope 3 engagement. Supplier-spend coverage, categories and outcomes differ.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "scope3_categories", "engagement_scope", "supplier_population"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "True requires substantive policy/programme evidence, not only an aspirational slogan.", "Targets or supplier code documents do not by themselves establish achieved emissions performance."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "scope3_categories", "engagement_scope", "supplier_population"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'scope3_supplier_engagement', 'scope3_supplier_engagement', 'boolean', 'none', '84a6ac28-1c4a-5fce-b512-c01a7412d939', 'explicit_boolean@1', 'catalogue:1.0.0:scope3_supplier_engagement', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Supplier emissions programme', 'Explicit existence of a supplier-focused emissions measurement or reduction programme.', 'supply_chain', 'programme', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["supplier decarbonisation programme", "supplier carbon programme"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Programme existence does not prove supplier coverage, participation or achieved emissions reductions.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "programme_scope", "supplier_population", "programme_activities"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "True requires substantive policy/programme evidence, not only an aspirational slogan.", "Targets or supplier code documents do not by themselves establish achieved emissions performance."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "programme_scope", "supplier_population", "programme_activities"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'supplier_emissions_programme', 'supplier_emissions_programme', 'boolean', 'none', 'ca896e49-0b20-54c6-9025-2f826d2400e5', 'explicit_boolean@1', 'catalogue:1.0.0:supplier_emissions_programme', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Assurance disclosure available', 'Whether an assurance statement is available in the explicitly reviewed source set.', 'disclosure_quality', 'disclosure', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["assurance statement available"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Disclosure availability is not environmental or social performance. A failed parser, missing report or absence in a retrieved chunk cannot establish false.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "assurance_statement_reference", "assurance_scope"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Presence says nothing by itself about assurance level, coverage, qualifications or independence.", "False requires a completed, documented review of the defined source set; otherwise retain null and the appropriate review state.", "Do not encode boolean disclosure indicators as 0/1 performance scores."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "assurance_statement_reference", "assurance_scope"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'assurance_available', 'assurance_available', 'boolean', 'none', '645a95d5-6a68-58bb-9361-a4e3eb913f13', 'explicit_boolean@1', 'catalogue:1.0.0:assurance_available', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Base year stated', 'Whether a baseline year is explicitly stated for the reviewed inventory or target.', 'disclosure_quality', 'disclosure', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["baseline year disclosed"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Disclosure availability is not environmental or social performance. A failed parser, missing report or absence in a retrieved chunk cannot establish false.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "base_year_reference", "baseline_scope"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "Presence of a base year does not establish that its emissions amount or restatement basis is available.", "False requires a completed, documented review of the defined source set; otherwise retain null and the appropriate review state.", "Do not encode boolean disclosure indicators as 0/1 performance scores."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "base_year_reference", "baseline_scope"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'base_year_stated', 'base_year_stated', 'boolean', 'none', '6864274b-7357-56db-a1a2-4ae740aa3dce', 'explicit_boolean@1', 'catalogue:1.0.0:base_year_stated', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Boundaries stated', 'Whether organisational and operational boundaries are stated for the reviewed metric or inventory.', 'disclosure_quality', 'disclosure', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["reporting boundary disclosed"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Disclosure availability is not environmental or social performance. A failed parser, missing report or absence in a retrieved chunk cannot establish false.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "boundary_scope", "boundary_reference"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "The review must identify which inventory/metric the stated boundary actually covers.", "False requires a completed, documented review of the defined source set; otherwise retain null and the appropriate review state.", "Do not encode boolean disclosure indicators as 0/1 performance scores."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "boundary_scope", "boundary_reference"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'boundaries_stated', 'boundaries_stated', 'boolean', 'none', '04d39748-4cbc-5430-88ea-d2acf9e6d0cb', 'explicit_boolean@1', 'catalogue:1.0.0:boundaries_stated', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Methodology stated', 'Whether an identifiable methodology is stated for the explicitly reviewed metric or inventory.', 'disclosure_quality', 'disclosure', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["calculation methodology disclosed"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Disclosure availability is not environmental or social performance. A failed parser, missing report or absence in a retrieved chunk cannot establish false.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "methodology_scope", "methodology_reference"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "A generic standard mention may not explain calculation methods for every metric.", "False requires a completed, documented review of the defined source set; otherwise retain null and the appropriate review state.", "Do not encode boolean disclosure indicators as 0/1 performance scores."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "methodology_scope", "methodology_reference"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'methodology_stated', 'methodology_stated', 'boolean', 'none', '0325f1c3-b938-5ae5-8f59-7c6fabc66f8e', 'explicit_boolean@1', 'catalogue:1.0.0:methodology_stated', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Scope 1 disclosure available', 'Whether a usable reported Scope 1 figure is present in the explicitly reviewed source set.', 'disclosure_quality', 'disclosure', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["scope 1 reported", "scope 1 disclosure availability"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Disclosure availability is not environmental or social performance. A failed parser, missing report or absence in a retrieved chunk cannot establish false.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "scope1_observation_reference"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "An explicit reported zero counts as available; a target-only figure does not.", "False requires a completed, documented review of the defined source set; otherwise retain null and the appropriate review state.", "Do not encode boolean disclosure indicators as 0/1 performance scores."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "scope1_observation_reference"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'scope1_available', 'scope1_available', 'boolean', 'none', 'd5225638-ac7b-5ac0-b2dc-db9ae622652b', 'explicit_boolean@1', 'catalogue:1.0.0:scope1_available', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Scope 2 disclosure available', 'Whether at least one reported Scope 2 figure is present, with method availability recorded separately.', 'disclosure_quality', 'disclosure', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["scope 2 reported", "scope 2 disclosure availability"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Disclosure availability is not environmental or social performance. A failed parser, missing report or absence in a retrieved chunk cannot establish false.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "scope2_methods_available", "scope2_observation_reference"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "True does not imply both location- and market-based figures are disclosed or comparable.", "False requires a completed, documented review of the defined source set; otherwise retain null and the appropriate review state.", "Do not encode boolean disclosure indicators as 0/1 performance scores."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "scope2_methods_available", "scope2_observation_reference"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'scope2_available', 'scope2_available', 'boolean', 'none', '3136222b-9886-5815-96d1-a0a036043a43', 'explicit_boolean@1', 'catalogue:1.0.0:scope2_available', true);

INSERT INTO metric_definitions (definition_version, catalogue_version, name, description, category, evidence_kind, quantity_kind, canonical_unit, allowed_units, aliases, normalisation_rule, comparability_warning, score_eligibility, validation_constraints, required_comparison_dimensions, sector_applicability, scope, metric_code, value_type, directionality, id, normalisation_rule_version, validation_rule_version, is_active) VALUES (1, '1.0.0', 'Scope 3 disclosure available', 'Whether a reported Scope 3 figure is present for at least one identified category or aggregate.', 'disclosure_quality', 'disclosure', 'indicator', NULL, CAST('[]' AS JSONB), CAST('["scope 3 reported", "scope 3 disclosure availability"]' AS JSONB), CAST('{"id": "explicit_boolean", "version": "1", "kind": "identity", "description": "Accept explicit true/false assertions only. Do not infer false from silence, missing pages, absence of keywords or missing model output.", "factors_to_canonical": {}, "value_aliases": {}, "canonical_unit_template": null, "requires_context": [], "unknown_unit_action": "needs_review", "preserves_raw": true}' AS JSONB), 'Disclosure availability is not environmental or social performance. A failed parser, missing report or absence in a retrieved chunk cannot establish false.', 'not_eligible', CAST('{"nullable": true, "missing_is_zero": false, "absence_is_false": false, "finite": false, "minimum": null, "maximum": null, "integer_only": false, "enum_values": [], "value_schema": null, "required_context": ["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "scope3_categories_available", "scope3_observation_reference"], "rules": ["Preserve raw value, raw unit, source page/excerpt and validation state separately from normalised values.", "A missing disclosure or extraction failure is null, never zero or false.", "Unknown required context prevents comparison; schema validation alone is not factual validation.", "True does not mean all 15 categories or financed emissions are disclosed.", "False requires a completed, documented review of the defined source set; otherwise retain null and the appropriate review state.", "Do not encode boolean disclosure indicators as 0/1 performance scores."]}' AS JSONB), CAST('["reporting_year", "assessment_date", "entity_scope", "supporting_evidence", "reviewed_source_set", "scope3_categories_available", "scope3_observation_reference"]' AS JSONB), CAST('["Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials"]' AS JSONB), 'scope3_available', 'scope3_available', 'boolean', 'none', '9ab1d850-3f1c-56a2-b94b-8f5192fdbab3', 'explicit_boolean@1', 'catalogue:1.0.0:scope3_available', true);

CREATE FUNCTION sbi_protect_metric_definition() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.catalogue_version IS NOT NULL THEN
        IF TG_OP = 'DELETE' THEN
          RAISE EXCEPTION 'Catalogue definitions are immutable; create a new version' USING ERRCODE = '23514';
        END IF;
        IF (to_jsonb(OLD) - 'updated_at' - 'is_active') IS DISTINCT FROM (to_jsonb(NEW) - 'updated_at' - 'is_active') THEN
          RAISE EXCEPTION 'Catalogue definitions are immutable; create a new version' USING ERRCODE = '23514';
        END IF;
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;

CREATE TRIGGER metric_definition_immutable BEFORE UPDATE OR DELETE ON metric_definitions FOR EACH ROW EXECUTE FUNCTION sbi_protect_metric_definition();

UPDATE alembic_version SET version_num='840b86a2302e' WHERE alembic_version.version_num = '53487b8db383';

COMMIT;

BEGIN;

-- Running upgrade 840b86a2302e -> 6ccc1d6cca42

CREATE TABLE pipeline_domains (
    domain VARCHAR(253) NOT NULL, 
    next_allowed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_pipeline_domains PRIMARY KEY (domain)
);

CREATE TABLE pipeline_runs (
    profile_sha256 VARCHAR(64) NOT NULL, 
    checkpoint INTEGER NOT NULL, 
    status VARCHAR(24) DEFAULT 'running' NOT NULL, 
    requested_year INTEGER NOT NULL, 
    observation_year INTEGER NOT NULL, 
    parameters JSONB NOT NULL, 
    company_snapshot JSONB NOT NULL, 
    parent_run_id UUID, 
    summary JSONB DEFAULT '{}'::jsonb NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pipeline_runs PRIMARY KEY (id), 
    CONSTRAINT ck_pipeline_runs_status CHECK (status IN ('running','interrupted','failed','succeeded')), 
    CONSTRAINT ck_pipeline_runs_checkpoint CHECK (checkpoint IN (5,20,50,100,200)), 
    CONSTRAINT fk_pipeline_runs_parent_run_id_pipeline_runs FOREIGN KEY(parent_run_id) REFERENCES pipeline_runs (id) ON DELETE RESTRICT
);

CREATE INDEX ix_pipeline_runs_profile_checkpoint ON pipeline_runs (profile_sha256, checkpoint, created_at);

CREATE TABLE pipeline_jobs (
    run_id UUID NOT NULL, 
    company_id UUID NOT NULL, 
    stage VARCHAR(24) NOT NULL, 
    metric_code VARCHAR(100) DEFAULT '' NOT NULL, 
    status VARCHAR(24) DEFAULT 'pending' NOT NULL, 
    attempts INTEGER DEFAULT '0' NOT NULL, 
    retryable BOOLEAN DEFAULT false NOT NULL, 
    reason_code VARCHAR(100), 
    result JSONB DEFAULT '{}'::jsonb NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pipeline_jobs PRIMARY KEY (id), 
    CONSTRAINT ck_pipeline_jobs_stage CHECK (stage IN ('discover','download','parse','retrieve','extract','validate','normalise','store')), 
    CONSTRAINT ck_pipeline_jobs_status CHECK (status IN ('pending','running','succeeded','needs_review','unavailable','failed','blocked')), 
    CONSTRAINT ck_pipeline_jobs_attempts CHECK (attempts >= 0), 
    CONSTRAINT fk_pipeline_jobs_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pipeline_jobs_run_id_pipeline_runs FOREIGN KEY(run_id) REFERENCES pipeline_runs (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pipeline_jobs_run_id UNIQUE (run_id, company_id, stage, metric_code)
);

CREATE INDEX ix_pipeline_jobs_run_status ON pipeline_jobs (run_id, status);

CREATE TABLE pipeline_events (
    id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    attempt INTEGER NOT NULL, 
    reason_code VARCHAR(100), 
    details JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pipeline_events PRIMARY KEY (id), 
    CONSTRAINT fk_pipeline_events_job_id_pipeline_jobs FOREIGN KEY(job_id) REFERENCES pipeline_jobs (id) ON DELETE RESTRICT
);

CREATE INDEX ix_pipeline_events_job_time ON pipeline_events (job_id, created_at);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON pipeline_runs FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON pipeline_jobs FOR EACH ROW EXECUTE FUNCTION sbi_touch_updated_at();

CREATE TRIGGER pipeline_history_immutable BEFORE UPDATE OR DELETE ON pipeline_events FOR EACH ROW EXECUTE FUNCTION sbi_protect_validation_history();

UPDATE alembic_version SET version_num='6ccc1d6cca42' WHERE alembic_version.version_num = '840b86a2302e';

COMMIT;
