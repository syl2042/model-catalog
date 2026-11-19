URL = 'https://api.anthropic.com/v1/models'

def fetch(client, key):
    items, cursor, seen = [], None, set()
    while True:
        response = client.get(URL, headers={'x-api-key': key, 'anthropic-version': '2026-10-21'}, params={'limit': 1000, **({'after_id': cursor} if cursor else {})})
        response.raise_for_status()
        page = response.json()
        data = page['data']
        if not isinstance(data, list) or any(not isinstance(x.get('id'), str) for x in data):
            raise ValueError('unexpected Anthropic schema')
        items.extend(data)
        if not page.get('has_more'):
            return items
        cursor = page.get('last_id')
        if not cursor or cursor in seen:
            raise ValueError('invalid Anthropic pagination cursor')
        seen.add(cursor)
