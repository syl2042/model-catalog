URL = 'https://models.dev/api.json'

def fetch(client):
    result = client.get(URL)
    result.raise_for_status()
    data = result.json()
    if not isinstance(data, dict) or not all(isinstance(data.get(p, {}).get('models'), dict) for p in ('openai', 'anthropic')):
        raise ValueError('unexpected Models.dev schema')
    return data
