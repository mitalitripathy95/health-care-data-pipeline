-- =============================================================================
-- Controlled orchestrator. Validates manifest, stages every Gold table,
-- validates controls, merges in dependency order, refreshes KPI evidence and
-- commits only when all steps pass. Any failure rolls the transaction back.
-- =============================================================================
CREATE OR REPLACE PROCEDURE RAW_STAGE.USP_PUBLISH_BATCH(
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
  v_manifest_result VARCHAR;
  v_audit_sk NUMBER;
  v_step_result VARCHAR;
  v_load_order NUMBER;
  v_table_name VARCHAR;
  v_merge_type VARCHAR;
  v_merge_procedure VARCHAR;
  v_failed BOOLEAN := FALSE;
BEGIN
  START TRANSACTION;

  INSERT INTO AUDIT.LOAD_AUDIT
    (BATCH_ID, MANIFEST_PATH, REPLAY_VERSION, STATUS, STARTED_AT)
  VALUES
    (:P_BATCH_ID, :P_MANIFEST_PATH, :P_REPLAY_VERSION, 'RUNNING', CURRENT_TIMESTAMP());

  v_manifest_result := RAW_STAGE.USP_VALIDATE_MANIFEST(:P_BATCH_ID, :P_MANIFEST_PATH, :P_REPLAY_VERSION);
  IF LEFT(v_manifest_result, 5) <> 'VALID' THEN
    UPDATE AUDIT.LOAD_AUDIT SET STATUS = 'MANIFEST_FAILED', ERROR_MESSAGE = :v_manifest_result,
           COMPLETED_AT = CURRENT_TIMESTAMP() WHERE BATCH_ID = :P_BATCH_ID;
    ROLLBACK;
    RETURN v_manifest_result;
  END IF;

  FOR record IN (
    SELECT TABLE_NAME, MERGE_TYPE, LOAD_ORDER
      FROM RAW_STAGE.LOAD_TABLE_CONTROL
     ORDER BY LOAD_ORDER
  ) DO
    v_table_name := record.TABLE_NAME;
    v_merge_type := record.MERGE_TYPE;
    v_load_order := record.LOAD_ORDER;

    v_step_result := RAW_STAGE.USP_LOAD_STAGING(:P_BATCH_ID, :v_table_name);
    IF LEFT(v_step_result, 6) <> 'LOADED' THEN
      v_failed := TRUE;
      EXIT;
    END IF;

    v_step_result := RAW_STAGE.USP_VALIDATE_STAGING(:P_BATCH_ID, :v_table_name);
    IF LEFT(v_step_result, 5) <> 'VALID' THEN
      v_failed := TRUE;
      EXIT;
    END IF;

    CASE v_merge_type
      WHEN 'SCD1' THEN v_merge_procedure := 'USP_MERGE_SCD1_DIMENSION';
      WHEN 'SCD2' THEN v_merge_procedure := 'USP_MERGE_SCD2_DIMENSION';
      WHEN 'FACT' THEN v_merge_procedure := 'USP_MERGE_FACT';
      ELSE v_merge_procedure := 'USP_MERGE_CURATED';
    END CASE;
    v_step_result := CALL IDENTIFIER('RAW_STAGE.' || v_merge_procedure)(:P_BATCH_ID, :v_table_name);
    IF LEFT(v_step_result, 6) <> 'MERGED' THEN
      v_failed := TRUE;
      EXIT;
    END IF;
  END FOR;

  IF v_failed THEN
    UPDATE AUDIT.LOAD_AUDIT SET STATUS = 'VALIDATION_FAILED', ERROR_MESSAGE = :v_step_result,
           COMPLETED_AT = CURRENT_TIMESTAMP() WHERE BATCH_ID = :P_BATCH_ID;
    ROLLBACK;
    RETURN 'ROLLED_BACK:' || :v_step_result;
  END IF;

  RAW_STAGE.USP_REFRESH_KPIS(:P_BATCH_ID);

  MERGE INTO AUDIT.PUBLISHED_BATCH p
  USING (SELECT :P_BATCH_ID AS BATCH_ID, RAW_STAGE.USP_MANIFEST_HASH(:P_BATCH_ID) AS MANIFEST_HASH, :P_REPLAY_VERSION AS REPLAY_VERSION) s
    ON p.BATCH_ID = s.BATCH_ID
  WHEN MATCHED THEN UPDATE SET PUBLISHED_AT = CURRENT_TIMESTAMP(), MANIFEST_HASH = s.MANIFEST_HASH, REPLAY_VERSION = s.REPLAY_VERSION
  WHEN NOT MATCHED THEN INSERT (BATCH_ID, MANIFEST_HASH, PUBLISHED_AT, REPLAY_VERSION)
                         VALUES (s.BATCH_ID, s.MANIFEST_HASH, CURRENT_TIMESTAMP(), s.REPLAY_VERSION);

  UPDATE AUDIT.LOAD_AUDIT SET STATUS = 'PUBLISHED', COMPLETED_AT = CURRENT_TIMESTAMP()
   WHERE BATCH_ID = :P_BATCH_ID;

  COMMIT;
  RETURN 'PUBLISHED:' || :P_BATCH_ID;
EXCEPTION
  WHEN OTHER THEN
    ROLLBACK;
    INSERT INTO AUDIT.LOAD_ERROR (BATCH_ID, ERROR_CODE, ERROR_MESSAGE)
    VALUES (:P_BATCH_ID, 'PUBLISH_EXCEPTION', SQLERRM);
    RETURN 'ROLLED_BACK:' || SQLERRM;
END;
$$;
