-- =============================================================================
-- COPY the exact manifest-listed Parquet files for one Gold table into its
-- batch-scoped transient staging table.
-- =============================================================================
CREATE OR REPLACE PROCEDURE RAW_STAGE.USP_LOAD_STAGING(
  P_BATCH_ID VARCHAR,
  P_TABLE_NAME VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  v_sql VARCHAR;
  v_files VARCHAR;
  v_loaded NUMBER;
  v_staging_name VARCHAR;
  v_select_list VARCHAR;
BEGIN
  v_staging_name := 'RAW_STAGE.STG_' || UPPER(:P_TABLE_NAME);
  IF (SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.TABLES
       WHERE UPPER(TABLE_SCHEMA) = 'RAW_STAGE'
         AND UPPER(TABLE_NAME) = UPPER('STG_' || :P_TABLE_NAME)) = 0 THEN
    RETURN 'ERROR: staging table not found';
  END IF;

  -- MATCH_BY_COLUMN_NAME cannot be combined with COPY transforms. Build an
  -- explicit projection from the Parquet root object so every type is cast
  -- against the controlled transient schema.
  SELECT LISTAGG(
           CASE DATA_TYPE
             WHEN 'NUMBER' THEN 'TRY_TO_NUMBER($1:"' || COLUMN_NAME || '"::VARCHAR) AS "' || COLUMN_NAME || '"'
             WHEN 'DECIMAL' THEN 'TRY_TO_NUMBER($1:"' || COLUMN_NAME || '"::VARCHAR) AS "' || COLUMN_NAME || '"'
             WHEN 'FLOAT' THEN 'TRY_TO_DOUBLE($1:"' || COLUMN_NAME || '"::VARCHAR) AS "' || COLUMN_NAME || '"'
             WHEN 'BOOLEAN' THEN 'TRY_TO_BOOLEAN($1:"' || COLUMN_NAME || '") AS "' || COLUMN_NAME || '"'
             WHEN 'DATE' THEN 'TRY_TO_DATE($1:"' || COLUMN_NAME || '"::VARCHAR) AS "' || COLUMN_NAME || '"'
             WHEN 'TIMESTAMP_NTZ' THEN 'TRY_TO_TIMESTAMP_NTZ($1:"' || COLUMN_NAME || '"::VARCHAR) AS "' || COLUMN_NAME || '"'
             ELSE '$1:"' || COLUMN_NAME || '"::VARCHAR AS "' || COLUMN_NAME || '"'
           END,
           ', '
         ) WITHIN GROUP (ORDER BY ORDINAL_POSITION)
    INTO :v_select_list
    FROM INFORMATION_SCHEMA.COLUMNS
   WHERE UPPER(TABLE_SCHEMA) = 'RAW_STAGE'
     AND UPPER(TABLE_NAME) = UPPER('STG_' || :P_TABLE_NAME)
     AND UPPER(COLUMN_NAME) NOT IN ('_COPY_FILE_NAME', '_COPY_ROW_NUMBER');

  IF v_select_list IS NULL THEN
    RETURN 'ERROR: staging columns not found';
  END IF;

  SELECT ARRAY_TO_STRING(
           ARRAY_AGG('''' || FILE_PATH || ''''),
           ', '
         )
    INTO :v_files
    FROM RAW_STAGE.MANIFEST_FILE
   WHERE BATCH_ID = :P_BATCH_ID
     AND TABLE_NAME = UPPER(:P_TABLE_NAME);

  IF v_files IS NULL THEN
    RETURN 'ERROR: no manifest files for table';
  END IF;

  -- Make staging replay-safe for the same batch and file set.
  v_sql := 'DELETE FROM ' || v_staging_name || ' WHERE _GOLD_BATCH_ID = ?';
  EXECUTE IMMEDIATE :v_sql USING (:P_BATCH_ID);

  v_sql := 'COPY INTO ' || v_staging_name ||
           ' FROM (SELECT ' || v_select_list ||
           ', METADATA$FILENAME AS "_COPY_FILE_NAME", METADATA$FILE_ROW_NUMBER AS "_COPY_ROW_NUMBER"' ||
           ' FROM @RAW_STAGE.STG_GOLD_EXPORT) ' ||
           'FILE_FORMAT = (TYPE = PARQUET) FILES = (' || v_files || ') ' ||
           'ON_ERROR = ''ABORT_STATEMENT'' PURGE = FALSE';
  EXECUTE IMMEDIATE :v_sql;

  v_sql := 'SELECT COUNT(*) FROM ' || v_staging_name || ' WHERE _GOLD_BATCH_ID = ?';
  EXECUTE IMMEDIATE :v_sql INTO :v_loaded USING (:P_BATCH_ID);
  RETURN 'LOADED:' || :P_TABLE_NAME || ':' || v_loaded;
EXCEPTION
  WHEN OTHER THEN
    RETURN 'ERROR: ' || SQLERRM;
END;
$$;
