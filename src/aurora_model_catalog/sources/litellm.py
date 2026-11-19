URL = 'https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json'

def fetch(client):
    result = client.get(URL)
    result.raise_for_status()
    data = result.json()
    if not isinstance(data, dict) or not any(isinstance(x, dict) and x.get('litellm_provider') in ('openai', 'anthropic') for x in data.values()):
        raise ValueError('unexpected LiteLLM schema')
    return data
