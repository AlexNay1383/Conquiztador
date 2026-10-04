import re

with open('config/settings.py', 'r') as f:
    content = f.read()

content = re.sub(
    r'(\s*)"accounts",\n]',
    r'\1"accounts",\n\1"questions",\n\1"games",\n]',
    content
)

with open('config/settings.py', 'w') as f:
    f.write(content)
