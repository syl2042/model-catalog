import argparse
import json
import sys
from pathlib import Path
from .catalog import DEFAULT_PATH, changes, load, sync

def main():
    parser = argparse.ArgumentParser(prog='aurora-model-catalog')
    sub = parser.add_subparsers(dest='command', required=True)
    for cmd in ('sync','sync-public','validate','list'):
        p = sub.add_parser(cmd); p.add_argument('--file', type=Path, default=DEFAULT_PATH)
    for cmd in ('sync-groups', 'validate-groups'):
        p = sub.add_parser(cmd)
        p.add_argument('--file', type=Path, default=Path('public/model-catalog.groups.v1.json'))
        p.add_argument('--catalog', type=Path, default=Path('public/model-catalog.v2.json'))
    for cmd in ('sync-clean', 'validate-clean'):
        p = sub.add_parser(cmd)
        p.add_argument('--file', type=Path, default=Path('public/model-catalog.json'))
        if cmd == 'sync-clean':
            p.add_argument('--catalog', type=Path, default=Path('public/model-catalog.v2.json'))
            p.add_argument('--groups', type=Path, default=Path('public/model-catalog.groups.v1.json'))
    p = sub.add_parser('diff'); p.add_argument('previous', type=Path); p.add_argument('current', type=Path, nargs='?', default=DEFAULT_PATH)
    args = parser.parse_args()
    try:
        if args.command in ('sync', 'sync-public'):
            if args.command == 'sync-public':
                from .public_catalog import sync_public, PUBLIC_PATH
                catalog = sync_public(PUBLIC_PATH if args.file == DEFAULT_PATH else args.file)
            else:
                catalog = sync(args.file)
            print(json.dumps({'status':catalog['sync_status']['status'], 'sources':catalog['sources'], 'changes':catalog['sync_status']['changes'], 'conflicts':len(catalog['sync_status']['conflicts']), 'checksum_sha256':catalog['checksum_sha256']}, indent=2))
        elif args.command in ('sync-clean','validate-clean'):
            from .clean_catalog import sync_clean, load_clean
            catalog = sync_clean(args.catalog,args.groups,args.file) if args.command == 'sync-clean' else load_clean(args.file)
            print(json.dumps({'models':len(catalog['models']), 'checksum_sha256':catalog['checksum_sha256']}, indent=2))
        elif args.command in ('sync-groups','validate-groups'):
            from .grouped_catalog import sync_index, load_index
            if args.command == 'sync-groups':
                index = sync_index(args.catalog, args.file)
            else:
                index = load_index(args.file, load(args.catalog))
            print(json.dumps({'groups':len(index['groups']), 'ungrouped':len(index['ungrouped']), 'catalog_checksum_sha256':index['catalog_checksum_sha256'], 'checksum_sha256':index['checksum_sha256']}, indent=2))
        elif args.command == 'validate':
            catalog = load(args.file); print(f"Valid: {len(catalog['models'])} models, SHA-256 {catalog['checksum_sha256']}")
        elif args.command == 'list':
            catalog = load(args.file)
            for ident,model in catalog['models'].items(): print(f"{ident}\t{model['identity']['display_name'] or ''}")
        else:
            print(json.dumps(changes(load(args.previous),load(args.current)), indent=2))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f'Error: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__': sys.exit(main())
