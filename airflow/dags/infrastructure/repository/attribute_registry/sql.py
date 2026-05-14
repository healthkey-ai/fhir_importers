FETCH_TRIAL_ATTRIBUTES_V2 = """
SELECT id, register, attribute, is_extracted
FROM prompts_attributeregistrystatus
{where}
ORDER BY id
LIMIT :limit OFFSET :offset;
"""

FETCH_TRIAL_ATTRIBUTES = """
SELECT register, attribute, is_extracted
FROM prompts_attributeregistrystatus
WHERE
    (:registry IS NULL OR register = :registry)
AND
    (:is_extracted IS NULL OR is_extracted = :is_extracted);
"""


UPDATE_IS_EXTRACTED = """
UPDATE prompts_attributeregistrystatus
SET is_extracted = TRUE
WHERE register = :registry
AND attribute IN :attributes;
"""
