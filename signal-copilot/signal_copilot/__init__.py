"""AI Signal Investigation Copilot.

Statistics detect, AI extracts (verified), rules decide, humans approve.
"""

MODEL_ID = "apac.amazon.nova-lite-v1:0"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
AWS_REGION = "ap-south-1"
MINUTES_PER_CASE = 15  # Assumption A4: manual review effort per case
