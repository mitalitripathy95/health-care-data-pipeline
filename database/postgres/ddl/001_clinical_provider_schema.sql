-- PostgreSQL clinical/provider source schema. Synthetic data only.
CREATE SCHEMA IF NOT EXISTS clinical;
CREATE OR REPLACE FUNCTION clinical.touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END; $$;
CREATE TABLE IF NOT EXISTS clinical.patients (
 patient_id BIGINT PRIMARY KEY, enterprise_person_id UUID NOT NULL, first_name VARCHAR(80) NOT NULL, last_name VARCHAR(80) NOT NULL,
 date_of_birth DATE NOT NULL, sex CHAR(1) NOT NULL CHECK (sex IN ('F','M','X','U')), email VARCHAR(254), phone VARCHAR(30),
 address_line1 VARCHAR(200), city VARCHAR(80), state_code CHAR(2), postal_code VARCHAR(12), synthetic_national_id VARCHAR(32) UNIQUE,
 source_schema_version VARCHAR(20) NOT NULL DEFAULT 'v1', created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS clinical.providers (
 provider_id BIGINT PRIMARY KEY, provider_external_id VARCHAR(40) NOT NULL UNIQUE, provider_name VARCHAR(160) NOT NULL,
 specialty VARCHAR(80) NOT NULL, npi_like VARCHAR(20) NOT NULL UNIQUE, updated_at TIMESTAMPTZ NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS clinical.facilities (
 facility_id BIGINT PRIMARY KEY, facility_name VARCHAR(160) NOT NULL, facility_type VARCHAR(40) NOT NULL,
 city VARCHAR(80) NOT NULL, state_code CHAR(2) NOT NULL, updated_at TIMESTAMPTZ NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS clinical.provider_facility_affiliation (
 affiliation_id BIGINT PRIMARY KEY, provider_id BIGINT NOT NULL REFERENCES clinical.providers(provider_id), facility_id BIGINT NOT NULL REFERENCES clinical.facilities(facility_id),
 effective_start_date DATE NOT NULL, effective_end_date DATE, updated_at TIMESTAMPTZ NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
 CHECK (effective_end_date IS NULL OR effective_end_date >= effective_start_date), UNIQUE(provider_id, facility_id, effective_start_date)
);
CREATE TABLE IF NOT EXISTS clinical.encounters (
 encounter_id BIGINT PRIMARY KEY, patient_id BIGINT NOT NULL REFERENCES clinical.patients(patient_id), provider_id BIGINT NOT NULL REFERENCES clinical.providers(provider_id), facility_id BIGINT NOT NULL REFERENCES clinical.facilities(facility_id),
 encounter_type VARCHAR(40) NOT NULL, encounter_start TIMESTAMPTZ NOT NULL, encounter_end TIMESTAMPTZ, status VARCHAR(20) NOT NULL, updated_at TIMESTAMPTZ NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
 CHECK (encounter_end IS NULL OR encounter_end >= encounter_start)
);
CREATE TABLE IF NOT EXISTS clinical.diagnoses (
 diagnosis_id BIGINT PRIMARY KEY, encounter_id BIGINT NOT NULL REFERENCES clinical.encounters(encounter_id), patient_id BIGINT NOT NULL REFERENCES clinical.patients(patient_id), diagnosis_code VARCHAR(20) NOT NULL, diagnosis_type VARCHAR(20) NOT NULL, sequence_number SMALLINT NOT NULL CHECK(sequence_number > 0), updated_at TIMESTAMPTZ NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS clinical.procedures (
 procedure_id BIGINT PRIMARY KEY, encounter_id BIGINT NOT NULL REFERENCES clinical.encounters(encounter_id), patient_id BIGINT NOT NULL REFERENCES clinical.patients(patient_id), procedure_code VARCHAR(20) NOT NULL, procedure_date DATE NOT NULL, updated_at TIMESTAMPTZ NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS clinical.observations (
 observation_id BIGINT PRIMARY KEY, encounter_id BIGINT NOT NULL REFERENCES clinical.encounters(encounter_id), patient_id BIGINT NOT NULL REFERENCES clinical.patients(patient_id), observation_code VARCHAR(30) NOT NULL, observation_value DECIMAL(12,3), unit VARCHAR(20), observed_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS clinical.medications (
 medication_id BIGINT PRIMARY KEY, medication_code VARCHAR(30) NOT NULL UNIQUE, medication_name VARCHAR(160) NOT NULL, therapeutic_class VARCHAR(80) NOT NULL, updated_at TIMESTAMPTZ NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS clinical.prescriptions (
 prescription_id BIGINT PRIMARY KEY, patient_id BIGINT NOT NULL REFERENCES clinical.patients(patient_id), encounter_id BIGINT REFERENCES clinical.encounters(encounter_id), medication_id BIGINT NOT NULL REFERENCES clinical.medications(medication_id), prescribed_date DATE NOT NULL, status VARCHAR(20) NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0), updated_at TIMESTAMPTZ NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS ix_patients_updated ON clinical.patients(updated_at,patient_id); CREATE INDEX IF NOT EXISTS ix_providers_updated ON clinical.providers(updated_at,provider_id); CREATE INDEX IF NOT EXISTS ix_facilities_updated ON clinical.facilities(updated_at,facility_id);
CREATE INDEX IF NOT EXISTS ix_affiliation_updated ON clinical.provider_facility_affiliation(updated_at,affiliation_id); CREATE INDEX IF NOT EXISTS ix_encounters_updated ON clinical.encounters(updated_at,encounter_id); CREATE INDEX IF NOT EXISTS ix_diagnoses_updated ON clinical.diagnoses(updated_at,diagnosis_id); CREATE INDEX IF NOT EXISTS ix_procedures_updated ON clinical.procedures(updated_at,procedure_id); CREATE INDEX IF NOT EXISTS ix_observations_updated ON clinical.observations(updated_at,observation_id); CREATE INDEX IF NOT EXISTS ix_medications_updated ON clinical.medications(updated_at,medication_id); CREATE INDEX IF NOT EXISTS ix_prescriptions_updated ON clinical.prescriptions(updated_at,prescription_id);
CREATE INDEX IF NOT EXISTS ix_encounters_patient ON clinical.encounters(patient_id,encounter_start); CREATE INDEX IF NOT EXISTS ix_encounters_provider ON clinical.encounters(provider_id,facility_id);
