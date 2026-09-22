import os

filepath = 'etl/config/etl_config.yaml'
with open(filepath, 'r') as f:
    content = f.read()

# Comment out the active block (lines 9-66 and 90-110)
# Actually, just regex replace the blocks.
import re
content = re.sub(r'^(schema:\n(?:  .*\n)*)', r'# \1', content, flags=re.MULTILINE)
content = re.sub(r'^(validation:\n(?:  .*\n)*)', r'# \1', content, flags=re.MULTILINE)
content = re.sub(r'^(transformation:\n(?:  .*\n)*)', r'# \1', content, flags=re.MULTILINE)
content = re.sub(r'^(target:\n(?:  .*\n)*)', r'# \1', content, flags=re.MULTILINE)

# Now uncomment the standby block
content = re.sub(r'^# (schema:\n(?:#   .*\n)*)', lambda m: m.group(1).replace('# ', ''), content, flags=re.MULTILINE)
content = re.sub(r'^# (validation:\n(?:#   .*\n)*)', lambda m: m.group(1).replace('# ', ''), content, flags=re.MULTILINE)
content = re.sub(r'^# (transformation:\n(?:#   .*\n)*)', lambda m: m.group(1).replace('# ', ''), content, flags=re.MULTILINE)
content = re.sub(r'^# (target:\n(?:#   .*\n)*)', lambda m: m.group(1).replace('# ', ''), content, flags=re.MULTILINE)

with open(filepath, 'w') as f:
    f.write(content)
print("Config switched!")
