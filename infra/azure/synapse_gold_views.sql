-- Query the gold layer in ADLS Gen2 from a Synapse serverless SQL pool without
-- moving it. Serverless charges per TB scanned ($5/TB, first 1 TB free each
-- month on the free account); the whole gold layer is a few MB.
--
-- Prerequisites: a Synapse workspace whose managed identity has
-- "Storage Blob Data Reader" on the storage account. Replace <account>.

CREATE DATABASE clinical_event_stream;
GO
USE clinical_event_stream;
GO

CREATE EXTERNAL DATA SOURCE gold
WITH (LOCATION = 'https://<account>.dfs.core.windows.net/gold');
GO

CREATE EXTERNAL FILE FORMAT parquet_zstd
WITH (FORMAT_TYPE = PARQUET);
GO

-- Views over each gold table; the schema is inferred from the parquet files.
CREATE OR ALTER VIEW dim_patient AS
SELECT * FROM OPENROWSET(BULK 'dim_patient.parquet', DATA_SOURCE = 'gold', FORMAT = 'PARQUET') AS r;
GO
CREATE OR ALTER VIEW fct_encounter AS
SELECT * FROM OPENROWSET(BULK 'fct_encounter.parquet', DATA_SOURCE = 'gold', FORMAT = 'PARQUET') AS r;
GO
CREATE OR ALTER VIEW fct_condition AS
SELECT * FROM OPENROWSET(BULK 'fct_condition.parquet', DATA_SOURCE = 'gold', FORMAT = 'PARQUET') AS r;
GO
CREATE OR ALTER VIEW mart_condition_pairs AS
SELECT * FROM OPENROWSET(BULK 'mart_condition_pairs.parquet', DATA_SOURCE = 'gold', FORMAT = 'PARQUET') AS r;
GO
CREATE OR ALTER VIEW mart_care_gaps AS
SELECT * FROM OPENROWSET(BULK 'mart_care_gaps.parquet', DATA_SOURCE = 'gold', FORMAT = 'PARQUET') AS r;
GO

-- The question, answered from Azure:
SELECT TOP 10 condition_a, condition_b, patients_with_both, lift
FROM mart_condition_pairs
ORDER BY patients_with_both DESC;
