/* Idempotent metadata seed for all 19 synthetic source tables. */
SET XACT_ABORT ON;
MERGE control.source_system AS t USING (VALUES
 ('clinical_provider','POSTGRESQL'),('member_claims','AZURE_SQL')
) s(source_name,engine) ON t.source_name=s.source_name
WHEN MATCHED THEN UPDATE SET engine=s.engine,enabled=1
WHEN NOT MATCHED THEN INSERT(source_name,engine) VALUES(s.source_name,s.engine);

WITH metadata(source_name,source_schema,source_table,load_type,primary_key_column,watermark_column,sensitivity_class,concurrency_group) AS (
 SELECT * FROM (VALUES
 ('clinical_provider','clinical','patients','INCREMENTAL','patient_id','updated_at','direct_identifier_phi','clinical'),
 ('clinical_provider','clinical','providers','INCREMENTAL','provider_id','updated_at','synthetic_identifier','clinical'),
 ('clinical_provider','clinical','facilities','INCREMENTAL','facility_id','updated_at','low','clinical'),
 ('clinical_provider','clinical','provider_facility_affiliation','INCREMENTAL','affiliation_id','updated_at','low','clinical'),
 ('clinical_provider','clinical','encounters','INCREMENTAL','encounter_id','updated_at','phi','clinical'),
 ('clinical_provider','clinical','diagnoses','INCREMENTAL','diagnosis_id','updated_at','phi','clinical'),
 ('clinical_provider','clinical','procedures','INCREMENTAL','procedure_id','updated_at','phi','clinical'),
 ('clinical_provider','clinical','observations','INCREMENTAL','observation_id','updated_at','phi','clinical'),
 ('clinical_provider','clinical','medications','FULL','medication_id',NULL,'low','clinical'),
 ('clinical_provider','clinical','prescriptions','INCREMENTAL','prescription_id','updated_at','phi','clinical'),
 ('member_claims','payer','members','INCREMENTAL','member_id','modified_at','direct_identifier_phi','payer'),
 ('member_claims','payer','plans','FULL','plan_id',NULL,'low','payer'),
 ('member_claims','payer','member_enrollment','INCREMENTAL','enrollment_id','modified_at','phi','payer'),
 ('member_claims','payer','claims','INCREMENTAL','claim_id','modified_at','phi_financial','payer'),
 ('member_claims','payer','claim_lines','INCREMENTAL','claim_line_id','modified_at','phi_financial','payer'),
 ('member_claims','payer','claim_diagnoses','INCREMENTAL','claim_diagnosis_id','modified_at','phi','payer'),
 ('member_claims','payer','authorizations','INCREMENTAL','authorization_id','modified_at','phi','payer'),
 ('member_claims','payer','payments','INCREMENTAL','payment_id','modified_at','phi_financial','payer'),
 ('member_claims','payer','claim_adjustments','INCREMENTAL','adjustment_id','modified_at','phi_financial','payer')
 ) v(source_name,source_schema,source_table,load_type,primary_key_column,watermark_column,sensitivity_class,concurrency_group)
), src AS (
 SELECT ss.source_system_id,m.*, CONCAT('SELECT * FROM ',m.source_schema,'.',m.source_table) extraction_sql_template,
 CONCAT('bronze/raw/source=',m.source_name,'/schema=',m.source_schema,'/table=',m.source_table) destination_path
 FROM metadata m JOIN control.source_system ss ON ss.source_name=m.source_name
)
MERGE control.ingestion_config AS t USING src s ON t.source_system_id=s.source_system_id AND t.source_schema=s.source_schema AND t.source_table=s.source_table
WHEN MATCHED THEN UPDATE SET load_type=s.load_type,primary_key_column=s.primary_key_column,watermark_column=s.watermark_column,extraction_sql_template=s.extraction_sql_template,destination_path=s.destination_path,target_format='PARQUET',expected_schema_version='v1',sensitivity_class=s.sensitivity_class,enabled=1,concurrency_group=s.concurrency_group,retry_count=3,dq_threshold=0
WHEN NOT MATCHED THEN INSERT(source_system_id,source_schema,source_table,load_type,primary_key_column,watermark_column,extraction_sql_template,destination_path,target_format,expected_schema_version,sensitivity_class,enabled,concurrency_group,retry_count,dq_threshold)
VALUES(s.source_system_id,s.source_schema,s.source_table,s.load_type,s.primary_key_column,s.watermark_column,s.extraction_sql_template,s.destination_path,'PARQUET','v1',s.sensitivity_class,1,s.concurrency_group,3,0);
