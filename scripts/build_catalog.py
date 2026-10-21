"""Rebuild versioned locale resources from the maintained translation tables."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sources=json.loads((ROOT/'scripts/legacy-messages.json').read_text())
rows=(ROOT/'scripts/legacy-translations.txt').read_text().splitlines()
assert len(rows)==len(sources),(len(rows),len(sources))
messages={}
for source,line in zip(sources,rows):
 en,pt=(value.replace('\\n','\n') for value in line.split('|||'))
 messages[source]={'en':en,'es':source,'pt-BR':pt}
for line in (ROOT/'scripts/translations.txt').read_text().splitlines():
 if not line or line.startswith('#'):continue
 en,es,pt=(value.replace('\\n','\n') for value in line.split('|||'))
 messages[en]={'en':en,'es':es,'pt-BR':pt}
(ROOT/'ptero/locales/messages.json').write_text(json.dumps(messages,ensure_ascii=False,indent=2)+'\n')
print(f'{len(messages)} translated messages in English, Spanish and Brazilian Portuguese')
