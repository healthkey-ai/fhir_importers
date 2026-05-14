WHERE_UNIVERSE_WRONG_VALUE = """
SELECT code
FROM trials_trial
WHERE id IN (
    SELECT DISTINCT trial_id
    FROM trials_trialwrongvalue
)
"""

SELECT_IDS_DYNAMIC_WHERE = """
SELECT id, code
FROM trials_trial
WHERE {where}
ORDER BY id LIMIT :limit
OFFSET :offset;
"""

SELECT_ALL_DYNAMIC_WHERE = """
SELECT *
FROM trials_trial
WHERE {where}
ORDER BY id LIMIT :limit
OFFSET :offset;
"""
