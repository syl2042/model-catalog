URL = 'https://api.openai.com/v1/models'

def fetch(client, key):
    response = client.get(URL, headers={'Authorization': f'Bearer {key}'})
    response.raise_for_status()
    data = response.json()['data']
    if not isinstance(data, list) or any(not isinstance(x.get('id'), str) for x in data):
        raise ValueError('unexpected OpenAI schema')
    return data
