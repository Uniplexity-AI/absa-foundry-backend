import os

path = r'services\decision-intelligence-service\app\api\catalog_routes.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Update add_campaign metadata
content = content.replace(
    '            "channel": item.channel,\n            "type": "campaign"\n        }],',
    '            "channel": item.channel,\n            "expires": item.expires,\n            "type": "campaign"\n        }],'
)

# Update update_campaign metadata
content = content.replace(
    '            "channel": item.channel,\n            "type": "campaign"\n        }]\n    )',
    '            "channel": item.channel,\n            "expires": item.expires,\n            "type": "campaign"\n        }]\n    )'
)

# Update list_campaigns item appending
content = content.replace(
    '                "target_segment": meta.get("target_segment", ""),\n                "channel": meta.get("channel", "")\n            })',
    '                "target_segment": meta.get("target_segment", ""),\n                "channel": meta.get("channel", ""),\n                "expires": meta.get("expires", "2026-12-31")\n            })'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated catalog_routes.py')
