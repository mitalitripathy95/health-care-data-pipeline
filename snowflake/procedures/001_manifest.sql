-- =============================================================================
-- Manifest ingestion and validation. The manifest is authoritative: only files
-- explicitly listed for a batch are eligible for COPY INTO.
-- =============================================================================
CREATE OR REPLACE PROCEDURE RAW_STAGE.USP_VALIDATE_MANIFEST(
  P_BATCH_ID VARCHAR,
  P_MANIFEST_PATH VARCHAR,
  P_REPLAY_VERSION VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  v_published NUMBER;
  v_manifest VARIANT;
  v_manifest_hash VARCHAR;
  v_table_count NUMBER;
  v_file_count NUMBER;
  v_expected_rows NUMBER;
  v_file_name VARCHAR;
BEGIN
  IF P_BATCH_ID IS NULL OR P_MANIFEST_PATH IS NULL THEN
    RETURN 'ERROR: batch_id and manifest_path are required';
  END IF;

  IF P_REPLAY_VERSION IS NULL THEN
    SELECT COUNT(*) INTO :v_published
    FROM AUDIT.PUBLISHED_BATCH
    WHERE BATCH_ID = :P_BATCH_ID;
    IF v_published > 0 THEN
      RETURN 'DUPLICATE_BATCH';
    END IF;
  END IF;

  DELETE FROM RAW_STAGE.MANIFEST_FILE WHERE BATCH_ID = :P_BATCH_ID;
  DELETE FROM RAW_STAGE.MANIFEST WHERE BATCH_ID = :P_BATCH_ID;

  COPY INTO RAW_STAGE.MANIFEST (BATCH_ID, MANIFEST_PATH, MANIFEST)
  FROM (
    SELECT :P_BATCH_ID, :P_MANIFEST_PATH, $1
    FROM @RAW_STAGE.STG_GOLD_EXPORT
  )
  FILE_FORMAT = (TYPE = JSON)
  FILES = (:P_MANIFEST_PATH)
  ON_ERROR = 'ABORT_STATEMENT';

  SELECT MANIFEST INTO :v_manifest FROM RAW_STAGE.MANIFEST WHERE BATCH_ID = :P_BATCH_ID;
  IF v_manifest IS NULL THEN
    RETURN 'ERROR: manifest file missing or empty';
  END IF;

  v_manifest_hash := SHA2(v_manifest::VARCHAR, 256);

  INSERT INTO RAW_STAGE.MANIFEST_FILE
    (BATCH_ID, TABLE_NAME, FILE_PATH, FILE_SHA256, FILE_SIZE_BYTES, ROW_COUNT)
  SELECT
    :P_BATCH_ID,
    UPPER(f:table::VARCHAR),
    f:path::VARCHAR,
    f:sha256::VARCHAR,
    TRY_TO_NUMBER(f:size_bytes::VARCHAR),
    TRY_TO_NUMBER(f:row_count::VARCHAR)
  FROM LATERAL FLATTEN(input => :v_manifest:files) f;

  SELECT COUNT(DISTINCT TABLE_NAME), COUNT(*), COALESCE(SUM(ROW_COUNT), 0)
    INTO :v_table_count, :v_file_count, :v_expected_rows
    FROM RAW_STAGE.MANIFEST_FILE
  WHERE BATCH_ID = :P_BATCH_ID;

  IF v_table_count = 0 OR v_file_count = 0 OR v_expected_rows < 0 THEN
    RETURN 'ERROR: invalid manifest counts';
  END IF;

  -- Every declared file must be visible through the integration-scoped stage.
  SELECT COUNT(*) INTO :v_file_count
  FROM RAW_STAGE.MANIFEST_FILE m
  WHERE m.BATCH_ID = :P_BATCH_ID
    AND NOT EXISTS (
      SELECT 1
        FROM TABLE(DIRECTORY(@RAW_STAGE.STG_GOLD_EXPORT)) d
       WHERE d.relative_path = m.FILE_PATH
         AND d.filesystem_exists = TRUE
    );
  IF v_file_count > 0 THEN
    RETURN 'ERROR: manifest files missing from stage count=' || v_file_count;
  END IF;

  RETURN 'VALID:' || v_table_count || ':' || v_file_count || ':' || v_expected_rows;
EXCEPTION
  WHEN OTHER THEN
    RETURN 'ERROR: ' || SQLERRM;
END;
$$;
