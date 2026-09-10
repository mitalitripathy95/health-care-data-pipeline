/* Phase 3 metadata, audit, locking, and publication schema.
   Safe to rerun. All data in this project is synthetic. */
SET XACT_ABORT ON;
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'control') EXEC('CREATE SCHEMA control');
GO
IF OBJECT_ID('control.source_system', 'U') IS NULL
CREATE TABLE control.source_system (
  source_system_id INT IDENTITY(1,1) NOT NULL CONSTRAINT pk_source_system PRIMARY KEY,
  source_name VARCHAR(50) NOT NULL CONSTRAINT uq_source_system_name UNIQUE,
  engine VARCHAR(30) NOT NULL CONSTRAINT ck_source_system_engine CHECK (engine IN ('POSTGRESQL','AZURE_SQL')),
  enabled BIT NOT NULL CONSTRAINT df_source_system_enabled DEFAULT 1,
  created_at DATETIME2(3) NOT NULL CONSTRAINT df_source_system_created DEFAULT SYSUTCDATETIME()
);
GO
IF OBJECT_ID('control.ingestion_config', 'U') IS NULL
CREATE TABLE control.ingestion_config (
  ingestion_config_id INT IDENTITY(1,1) NOT NULL CONSTRAINT pk_ingestion_config PRIMARY KEY,
  source_system_id INT NOT NULL CONSTRAINT fk_config_source REFERENCES control.source_system(source_system_id),
  source_schema VARCHAR(128) NOT NULL,
  source_table VARCHAR(128) NOT NULL,
  load_type VARCHAR(20) NOT NULL CONSTRAINT ck_config_load_type CHECK (load_type IN ('FULL','INCREMENTAL')),
  primary_key_column VARCHAR(128) NOT NULL,
  watermark_column VARCHAR(128) NULL,
  extraction_sql_template NVARCHAR(2000) NOT NULL,
  destination_path VARCHAR(500) NOT NULL,
  target_format VARCHAR(20) NOT NULL CONSTRAINT df_config_format DEFAULT 'PARQUET',
  expected_schema_version VARCHAR(20) NOT NULL,
  sensitivity_class VARCHAR(40) NOT NULL CONSTRAINT df_config_sensitivity DEFAULT 'synthetic',
  enabled BIT NOT NULL CONSTRAINT df_config_enabled DEFAULT 1,
  concurrency_group VARCHAR(50) NOT NULL CONSTRAINT df_config_group DEFAULT 'default',
  retry_count TINYINT NOT NULL CONSTRAINT df_config_retry DEFAULT 3,
  dq_threshold DECIMAL(5,2) NOT NULL CONSTRAINT df_config_dq DEFAULT 0,
  CONSTRAINT uq_ingestion_config UNIQUE(source_system_id, source_schema, source_table),
  CONSTRAINT ck_incremental_watermark CHECK (load_type = 'FULL' OR watermark_column IS NOT NULL)
);
GO
IF OBJECT_ID('control.pipeline_run', 'U') IS NULL
CREATE TABLE control.pipeline_run (
  pipeline_run_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT pk_pipeline_run PRIMARY KEY,
  batch_id VARCHAR(100) NOT NULL CONSTRAINT uq_pipeline_batch UNIQUE,
  pipeline_name VARCHAR(200) NOT NULL,
  invocation_type VARCHAR(20) NOT NULL CONSTRAINT df_pipeline_invocation DEFAULT 'MANUAL',
  status VARCHAR(20) NOT NULL CONSTRAINT ck_pipeline_status CHECK(status IN ('RUNNING','SUCCEEDED','FAILED')),
  started_at DATETIME2(3) NOT NULL,
  ended_at DATETIME2(3) NULL,
  error_message NVARCHAR(2000) NULL
);
GO
IF OBJECT_ID('control.table_run', 'U') IS NULL
CREATE TABLE control.table_run (
  table_run_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT pk_table_run PRIMARY KEY,
  pipeline_run_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT fk_table_pipeline REFERENCES control.pipeline_run(pipeline_run_id),
  ingestion_config_id INT NOT NULL CONSTRAINT fk_table_config REFERENCES control.ingestion_config(ingestion_config_id),
  adf_activity_run_id VARCHAR(100) NULL,
  status VARCHAR(20) NOT NULL CONSTRAINT ck_table_status CHECK(status IN ('RUNNING','SUCCEEDED','FAILED','SKIPPED')),
  low_watermark_ts DATETIME2(3) NULL, low_watermark_key VARCHAR(200) NULL,
  high_watermark_ts DATETIME2(3) NULL, high_watermark_key VARCHAR(200) NULL,
  row_count BIGINT NULL, file_count INT NULL,
  bronze_path VARCHAR(500) NULL,
  started_at DATETIME2(3) NOT NULL, ended_at DATETIME2(3) NULL,
  error_message NVARCHAR(2000) NULL,
  CONSTRAINT uq_table_run UNIQUE(pipeline_run_id, ingestion_config_id)
);
GO
IF OBJECT_ID('control.watermark_state', 'U') IS NULL
CREATE TABLE control.watermark_state (
  ingestion_config_id INT NOT NULL CONSTRAINT pk_watermark PRIMARY KEY CONSTRAINT fk_watermark_config REFERENCES control.ingestion_config(ingestion_config_id),
  last_committed_ts DATETIME2(3) NULL,
  last_committed_key VARCHAR(200) NULL,
  last_table_run_id UNIQUEIDENTIFIER NULL,
  updated_at DATETIME2(3) NOT NULL CONSTRAINT df_watermark_updated DEFAULT SYSUTCDATETIME()
);
GO
IF OBJECT_ID('control.ingestion_lock', 'U') IS NULL
CREATE TABLE control.ingestion_lock (
  ingestion_config_id INT NOT NULL CONSTRAINT pk_ingestion_lock PRIMARY KEY CONSTRAINT fk_lock_config REFERENCES control.ingestion_config(ingestion_config_id),
  owner_table_run_id UNIQUEIDENTIFIER NOT NULL,
  acquired_at DATETIME2(3) NOT NULL,
  expires_at DATETIME2(3) NOT NULL
);
GO
IF COL_LENGTH('control.ingestion_lock','owner_run_id') IS NOT NULL
   AND COL_LENGTH('control.ingestion_lock','owner_table_run_id') IS NULL
 EXEC sp_rename 'control.ingestion_lock.owner_run_id','owner_table_run_id','COLUMN';
GO
IF OBJECT_ID('control.batch_manifest', 'U') IS NULL
CREATE TABLE control.batch_manifest (
  manifest_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT pk_batch_manifest PRIMARY KEY,
  batch_id VARCHAR(100) NOT NULL,
  table_run_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT fk_manifest_table_run REFERENCES control.table_run(table_run_id),
  source_row_count BIGINT NOT NULL, landed_row_count BIGINT NOT NULL,
  checksum_sha256 CHAR(64) NOT NULL, schema_hash_sha256 CHAR(64) NOT NULL,
  bronze_path VARCHAR(500) NOT NULL, published_at DATETIME2(3) NULL,
  status VARCHAR(20) NOT NULL CONSTRAINT ck_manifest_status CHECK(status IN ('PUBLISHED','REJECTED')),
  CONSTRAINT uq_manifest_table_run UNIQUE(table_run_id),
  CONSTRAINT uq_manifest_batch_path UNIQUE(batch_id, bronze_path)
);
GO
IF OBJECT_ID('control.dq_result', 'U') IS NULL
CREATE TABLE control.dq_result (dq_result_id BIGINT IDENTITY PRIMARY KEY, batch_id VARCHAR(100) NOT NULL, domain VARCHAR(50) NOT NULL, table_name VARCHAR(128) NOT NULL, rule_name VARCHAR(200) NOT NULL, severity VARCHAR(20) NOT NULL, passed BIT NOT NULL, failed_count BIGINT NOT NULL DEFAULT 0, evaluated_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(), details NVARCHAR(2000) NULL);
GO
IF OBJECT_ID('control.job_dependency', 'U') IS NULL
CREATE TABLE control.job_dependency (job_dependency_id BIGINT IDENTITY PRIMARY KEY, batch_id VARCHAR(100) NOT NULL, upstream_job VARCHAR(200) NOT NULL, downstream_job VARCHAR(200) NOT NULL, status VARCHAR(20) NOT NULL, CONSTRAINT uq_job_dependency UNIQUE(batch_id,upstream_job,downstream_job));
GO
IF OBJECT_ID('control.reprocess_request', 'U') IS NULL
CREATE TABLE control.reprocess_request (request_id VARCHAR(100) PRIMARY KEY, domain VARCHAR(50) NOT NULL, start_business_date DATE NOT NULL, end_business_date DATE NOT NULL, business_key_range VARCHAR(500) NULL, reason NVARCHAR(1000) NOT NULL, requested_by VARCHAR(200) NOT NULL, code_version VARCHAR(100) NOT NULL, contract_version VARCHAR(20) NOT NULL, mode VARCHAR(20) NOT NULL CHECK(mode IN ('DRY_RUN','EXECUTE')), status VARCHAR(20) NOT NULL DEFAULT 'REQUESTED', created_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME());
GO
IF OBJECT_ID('control.reconciliation_result', 'U') IS NULL
CREATE TABLE control.reconciliation_result (reconciliation_id BIGINT IDENTITY PRIMARY KEY, batch_id VARCHAR(100) NOT NULL, domain VARCHAR(50) NOT NULL, source_count BIGINT NOT NULL, silver_count BIGINT NOT NULL, gold_count BIGINT NOT NULL, source_amount DECIMAL(18,2) NULL, gold_amount DECIMAL(18,2) NULL, passed BIT NOT NULL, evaluated_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME());
GO
IF OBJECT_ID('control.pipeline_health', 'U') IS NULL
CREATE TABLE control.pipeline_health (health_id BIGINT IDENTITY PRIMARY KEY, check_name VARCHAR(200) NOT NULL, status VARCHAR(20) NOT NULL, observed_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(), details NVARCHAR(2000) NULL);
GO
CREATE OR ALTER PROCEDURE control.usp_begin_pipeline_run
 @pipeline_run_id UNIQUEIDENTIFIER, @batch_id VARCHAR(100), @pipeline_name VARCHAR(200), @invocation_type VARCHAR(20)
AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS (SELECT 1 FROM control.pipeline_run WHERE batch_id=@batch_id AND status='SUCCEEDED') THROW 51001, 'Batch is already published successfully.', 1;
 IF EXISTS (SELECT 1 FROM control.pipeline_run WHERE batch_id=@batch_id AND status='RUNNING') THROW 51002, 'Batch is already running.', 1;
 INSERT control.pipeline_run(pipeline_run_id,batch_id,pipeline_name,invocation_type,status,started_at)
 VALUES(@pipeline_run_id,@batch_id,@pipeline_name,@invocation_type,'RUNNING',SYSUTCDATETIME());
END;
GO
CREATE OR ALTER PROCEDURE control.usp_finish_pipeline_run
 @pipeline_run_id UNIQUEIDENTIFIER, @status VARCHAR(20), @error_message NVARCHAR(2000)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 IF @status NOT IN ('SUCCEEDED','FAILED') THROW 51007, 'Pipeline terminal status must be SUCCEEDED or FAILED.', 1;
 UPDATE control.pipeline_run SET status=@status, ended_at=SYSUTCDATETIME(), error_message=@error_message WHERE pipeline_run_id=@pipeline_run_id;
 IF @@ROWCOUNT<>1 THROW 51008, 'Unknown pipeline run.', 1;
END;
GO
CREATE OR ALTER PROCEDURE control.usp_begin_table_run
 @table_run_id UNIQUEIDENTIFIER, @pipeline_run_id UNIQUEIDENTIFIER, @ingestion_config_id INT, @lock_minutes INT=120
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON; BEGIN TRAN;
 DELETE control.ingestion_lock WHERE ingestion_config_id=@ingestion_config_id AND expires_at<SYSUTCDATETIME();
 IF EXISTS (SELECT 1 FROM control.ingestion_lock WITH (UPDLOCK,HOLDLOCK) WHERE ingestion_config_id=@ingestion_config_id) BEGIN ROLLBACK; THROW 51003, 'Table ingestion lock is held by another run.', 1; END;
 INSERT control.ingestion_lock VALUES(@ingestion_config_id,@table_run_id,SYSUTCDATETIME(),DATEADD(MINUTE,@lock_minutes,SYSUTCDATETIME()));
 INSERT control.table_run(table_run_id,pipeline_run_id,ingestion_config_id,status,started_at) VALUES(@table_run_id,@pipeline_run_id,@ingestion_config_id,'RUNNING',SYSUTCDATETIME());
 COMMIT;
END;
GO
CREATE OR ALTER PROCEDURE control.usp_publish_table_run
 @table_run_id UNIQUEIDENTIFIER, @batch_id VARCHAR(100), @low_ts DATETIME2(3)=NULL, @low_key VARCHAR(200)=NULL,
 @high_ts DATETIME2(3)=NULL, @high_key VARCHAR(200)=NULL, @source_rows BIGINT, @landed_rows BIGINT,
 @file_count INT=1, @bronze_path VARCHAR(500), @advance_watermark BIT=1
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 IF @source_rows<>@landed_rows THROW 51004, 'Source and landed row counts do not reconcile.', 1;
 BEGIN TRAN;
 DECLARE @config_id INT, @schema_version VARCHAR(20), @load_type VARCHAR(20);
 SELECT @config_id=tr.ingestion_config_id,@schema_version=ic.expected_schema_version,@load_type=ic.load_type FROM control.table_run tr JOIN control.ingestion_config ic ON ic.ingestion_config_id=tr.ingestion_config_id WHERE tr.table_run_id=@table_run_id;
 IF @config_id IS NULL BEGIN ROLLBACK; THROW 51005, 'Unknown table run.', 1; END;
 UPDATE control.table_run SET status='SUCCEEDED',low_watermark_ts=@low_ts,low_watermark_key=@low_key,high_watermark_ts=@high_ts,high_watermark_key=@high_key,row_count=@landed_rows,file_count=@file_count,bronze_path=@bronze_path,ended_at=SYSUTCDATETIME() WHERE table_run_id=@table_run_id AND status='RUNNING';
 IF @@ROWCOUNT<>1 BEGIN ROLLBACK; THROW 51006, 'Table run is not publishable.', 1; END;
 INSERT control.batch_manifest(manifest_id,batch_id,table_run_id,source_row_count,landed_row_count,checksum_sha256,schema_hash_sha256,bronze_path,published_at,status)
 VALUES(NEWID(),@batch_id,@table_run_id,@source_rows,@landed_rows,CONVERT(CHAR(64),HASHBYTES('SHA2_256',CONCAT(@batch_id,'|',@bronze_path,'|',@landed_rows)),2),CONVERT(CHAR(64),HASHBYTES('SHA2_256',@schema_version),2),@bronze_path,SYSUTCDATETIME(),'PUBLISHED');
 /* checksum_sha256 is a landing-integrity metadata checksum over batch/path/count.
    It is intentionally not represented as a Parquet file-content checksum. */
 IF @load_type='INCREMENTAL' AND @advance_watermark=1 AND @high_ts IS NOT NULL
 MERGE control.watermark_state AS t USING (SELECT @config_id id) s ON t.ingestion_config_id=s.id
 WHEN MATCHED THEN UPDATE SET last_committed_ts=@high_ts,last_committed_key=@high_key,last_table_run_id=@table_run_id,updated_at=SYSUTCDATETIME()
 WHEN NOT MATCHED THEN INSERT(ingestion_config_id,last_committed_ts,last_committed_key,last_table_run_id) VALUES(@config_id,@high_ts,@high_key,@table_run_id);
 DELETE control.ingestion_lock WHERE ingestion_config_id=@config_id AND owner_table_run_id=@table_run_id;
 COMMIT;
END;
GO
CREATE OR ALTER PROCEDURE control.usp_fail_table_run @table_run_id UNIQUEIDENTIFIER, @error_message NVARCHAR(2000)
AS
BEGIN
 SET NOCOUNT ON; DECLARE @config_id INT=(SELECT ingestion_config_id FROM control.table_run WHERE table_run_id=@table_run_id);
 UPDATE control.table_run SET status='FAILED',ended_at=SYSUTCDATETIME(),error_message=LEFT(@error_message,2000) WHERE table_run_id=@table_run_id AND status='RUNNING';
 DELETE control.ingestion_lock WHERE ingestion_config_id=@config_id AND owner_table_run_id=@table_run_id;
END;
GO
CREATE OR ALTER PROCEDURE control.usp_publish_job_dependency
 @batch_id VARCHAR(100), @upstream_job VARCHAR(200), @downstream_job VARCHAR(200), @status VARCHAR(20)
AS
BEGIN
 SET NOCOUNT ON;
 IF @status NOT IN ('READY','BLOCKED','COMPLETED') THROW 51009, 'Unsupported job dependency status.', 1;
 MERGE control.job_dependency AS t
 USING (SELECT @batch_id batch_id,@upstream_job upstream_job,@downstream_job downstream_job,@status status) s
 ON t.batch_id=s.batch_id AND t.upstream_job=s.upstream_job AND t.downstream_job=s.downstream_job
 WHEN MATCHED THEN UPDATE SET status=s.status
 WHEN NOT MATCHED THEN INSERT(batch_id,upstream_job,downstream_job,status)
 VALUES(s.batch_id,s.upstream_job,s.downstream_job,s.status);
END;
GO
