-- =============================================================================
-- Table-level validation before publication. Fails fast on null keys,
-- duplicate surrogate keys, or row-count mismatch against the manifest.
-- =============================================================================
CREATE OR REPLACE PROCEDURE RAW_STAGE.USP_VALIDATE_STAGING(
  P_BATCH_ID VARCHAR,
  P_TABLE_NAME VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  v_actual NUMBER;
  v_null_keys NUMBER;
  v_duplicate_keys NUMBER;
  v_expected NUMBER;
  v_merge_key VARCHAR;
  v_sql VARCHAR;
BEGIN
  SELECT COALESCE(SUM(ROW_COUNT), 0), UPPER(MERGE_KEY)
    INTO :v_expected, :v_merge_key
    FROM RAW_STAGE.MANIFEST_FILE m
   WHERE m.BATCH_ID = :P_BATCH_ID
     AND m.TABLE_NAME = UPPER(:P_TABLE_NAME)
   GROUP BY MERGE_KEY;

  IF v_merge_key IS NULL THEN
    SELECT UPPER(MERGE_KEY)
      INTO :v_merge_key
      FROM RAW_STAGE.LOAD_TABLE_CONTROL
     WHERE UPPER(TABLE_NAME) = UPPER(:P_TABLE_NAME);
  END IF;

  IF v_merge_key IS NULL THEN
    RETURN 'ERROR: table not controlled';
  END IF;

  v_sql := 'SELECT COUNT(*), COUNT_IF("' || v_merge_key || '" IS NULL), COUNT(*) - COUNT(DISTINCT "' ||
           v_merge_key || '") FROM RAW_STAGE.STG_' || UPPER(:P_TABLE_NAME) ||
           ' WHERE _GOLD_BATCH_ID = ?';
  EXECUTE IMMEDIATE :v_sql INTO :v_actual, :v_null_keys, :v_duplicate_keys USING (:P_BATCH_ID);

  IF v_actual <> v_expected THEN
    RETURN 'ERROR: row_count_mismatch expected=' || v_expected || ' actual=' || v_actual;
  END IF;
  IF v_null_keys > 0 OR v_duplicate_keys > 0 THEN
    RETURN 'ERROR: merge_key_invalid nulls=' || v_null_keys || ' duplicates=' || v_duplicate_keys;
  END IF;
    INTO :v_expected
    FROM RAW_STAGE.MANIFEST_FILE m,
         LATERAL FLATTEN(input => m.MANIFEST) f
   WHERE m.BATCH_ID = :P_BATCH_ID
     AND m.TABLE_NAME = UPPER(:P_TABLE_NAME);

  v_sql := 'SELECT COUNT(*), COUNT_IF(SURROGATE_KEY IS NULL), COUNT(*) - COUNT(DISTINCT SURROGATE_KEY) FROM RAW_STAGE.STG_' || UPPER(:P_TABLE_NAME) || ' WHERE _GOLD_BATCH_ID = ?';
  EXECUTE IMMEDIATE :v_sql INTO :v_actual, :v_null_keys, :v_duplicate_keys USING (:P_BATCH_ID);

  IF v_actual <> v_expected THEN
    RETURN 'ERROR: row_count_mismatch expected=' || v_expected || ' actual=' || v_actual;
  END IF;
  IF v_null_keys > 0 OR v_duplicate_keys > 0 THEN
    RETURN 'ERROR: surrogate_key_invalid nulls=' || v_null_keys || ' duplicates=' || v_duplicate_keys;
  END IF;

  INSERT INTO AUDIT.RECONCILIATION
    (BATCH_ID, TABLE_NAME, CONTROL_NAME, EXPECTED_ROWS, ACTUAL_ROWS, STATUS)
  VALUES
    (:P_BATCH_ID, UPPER(:P_TABLE_NAME), 'ROW_COUNT', v_expected, v_actual, 'PASS');

  RETURN 'VALID:' || UPPER(:P_TABLE_NAME) || ':' || v_actual;
EXCEPTION
  WHEN OTHER THEN
    RETURN 'ERROR: ' || SQLERRM;
END;
$$;
