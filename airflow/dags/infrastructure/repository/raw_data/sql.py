SELECT_ALL = """
SELECT record_id, source_name, raw_data, created_at, updated_at
FROM trials_rawdataitem
ORDER BY id
LIMIT :limit OFFSET :offset;
"""

SELECT_REGISTER = """
SELECT record_id, source_name, raw_data, created_at, updated_at
FROM trials_rawdataitem
WHERE source_name = :source_name
ORDER BY id
LIMIT :limit OFFSET :offset;
"""

SELECT_BY_NATURAL_ID = """
SELECT record_id, source_name, raw_data FROM trials_rawdataitem WHERE record_id = :record_id;
"""

INSERT_OR_UPDATE = """
INSERT INTO trials_rawdataitem (record_id, source_name, raw_data, created_at, updated_at, old_raw_data, extracted_data)
VALUES (:record_id, :source_name, :raw_data, NOW(), NOW(), '{}', '{}')
ON CONFLICT (record_id) DO UPDATE
SET source_name = EXCLUDED.source_name,
raw_data = EXCLUDED.raw_data,
updated_at = NOW();
"""
