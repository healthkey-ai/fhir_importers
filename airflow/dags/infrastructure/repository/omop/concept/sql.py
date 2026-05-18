SELECT_BY_ID = """
SELECT concept_id, concept_name, concept_code, vocabulary_id
FROM concept
WHERE concept_id = :concept_id
LIMIT 1
"""

SELECT_BY_CODE = """
SELECT concept_id, concept_name, concept_code, vocabulary_id
FROM concept
WHERE concept_code = :code AND vocabulary_id = :vocabulary_id
LIMIT 1
"""

SELECT_BY_NAME_LIKE = """
SELECT concept_id, concept_name, concept_code, vocabulary_id
FROM concept
WHERE concept_name ILIKE :pattern
ORDER BY length(concept_name)
LIMIT 1
"""
