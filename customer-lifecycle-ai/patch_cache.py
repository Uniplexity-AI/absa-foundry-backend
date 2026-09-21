import re

file_path = 'services/decision-intelligence-service/app/api/routes.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add the cache dictionary
if '_NBA_CACHE: dict[str, dict] = {}' not in content:
    content = content.replace(
        '@router.get("/{customer_id}/nba")',
        '_NBA_CACHE: dict[str, dict] = {}\n\n@router.get("/{customer_id}/nba")'
    )

# Inject the cache check and set logic
cache_check = """
    try:
        # Check cache to simulate pre-computed nightly inference
        if customer_id in _NBA_CACHE:
            return _NBA_CACHE[customer_id]

        # Build the context and fetch candidates"""

content = content.replace(
    '    try:\n        # Build the context and fetch candidates',
    cache_check
)

cache_set = """        decision = await engine.determine_next_best_action_async(context_dict, candidate_strings)
        
        # Save to cache
        _NBA_CACHE[customer_id] = decision
        
        # The frontend AiNbaPanel expects certain keys. If the LLM generates them, return as-is.
        # But we must map to the shape expected by AiNbaPanel.
        return decision"""

content = content.replace(
    """        decision = await engine.determine_next_best_action_async(context_dict, candidate_strings)
        
        # The frontend AiNbaPanel expects certain keys. If the LLM generates them, return as-is.
        # But we must map to the shape expected by AiNbaPanel.
        return decision""",
    cache_set
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Added caching to NBA route")
