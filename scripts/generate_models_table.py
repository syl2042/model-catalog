#!/usr/bin/env python3
"""Create a versioned inventory of explicitly grouped canonical models."""
import argparse
import collections
import html
import json
from pathlib import Path

import httpx
from aurora_model_catalog.clean_catalog import validate_clean

URL = 'https://models-catalog.auroramind.fr/model-catalog.json'

def text(value):
    return html.escape(str(value), quote=False).replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')

def render(catalog):
    grouped = collections.defaultdict(list)
    unresolved = 0
    for model in catalog['models'].values():
        if model['grouping'] != 'canonical':
            unresolved += 1
            continue
        reference = model['canonical_ref']
        if not isinstance(reference, str) or '/' not in reference:
            raise ValueError('invalid canonical model reference')
        creator = reference.split('/', 1)[0]
        grouped[creator].append((reference, model['display_name'] or reference))
    total = sum(len(items) for items in grouped.values())
    lines = [
        '# Canonical model inventory / Inventaire des modèles canoniques', '',
        f"Catalog generated / Catalogue généré : `{text(catalog['generated_at'])}`  ",
        f"Catalog checksum / Empreinte du catalogue : `{text(catalog['checksum_sha256'])}`  ",
        f"Canonical models / Modèles canoniques : **{total}**  ",
        f"Creator namespaces / Espaces de noms créateurs : **{len(grouped)}**  ",
        f"Unresolved references not counted / Références non résolues non comptées : **{unresolved}**", '',
        'This is a snapshot, not a live list. Canonical versions are counted separately. '
        'The list includes language, image, audio, embedding and other models. '
        'Creator namespaces may represent organizations rather than direct API providers. '
        'A listing does not guarantee that a model is active or accessible to your account.', '',
        "Cet inventaire est un instantané, pas une liste en temps réel. Les versions canoniques sont comptées séparément. "
        "Il comprend des modèles de langage, d'image, d'audio, d'embedding et d'autres types. "
        "Les espaces de noms peuvent désigner des organisations plutôt que des fournisseurs d'API directs. "
        "Une référence ne garantit ni l'activité du modèle ni son accès à votre compte.", '',
        f'[Current catalog / Catalogue actuel]({URL})', '',
        '## Creators / Créateurs', '', '| Creator / Créateur | Canonical models / Modèles canoniques |', '| --- | ---: |'
    ]
    for creator, items in sorted(grouped.items(), key=lambda x: (-len(x[1]), x[0])):
        lines.append(f'| {text(creator)} | {len(items)} |')
    lines.extend(['', '## Models / Modèles', '',
                  '| Creator / Créateur | Name / Nom | Canonical reference / Référence canonique |', '| --- | --- | --- |'])
    for creator, items in sorted(grouped.items()):
        for reference, name in sorted(items):
            lines.append(f'| {text(creator)} | {text(name)} | {text(reference)} |')
    return '\n'.join(lines) + '\n'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', default=URL, help='HTTPS URL or local catalog file')
    parser.add_argument('--output', default='MODELS.md')
    args=parser.parse_args()
    if args.catalog.startswith('https://'):
        response=httpx.get(args.catalog,timeout=90,follow_redirects=True)
        response.raise_for_status()
        data=response.json()
    else:
        with open(args.catalog,encoding='utf-8') as f: data=json.load(f)
    catalog=validate_clean(data)
    Path(args.output).write_text(render(catalog),encoding='utf-8')
    print(f"Wrote {args.output}")

if __name__ == '__main__': main()
