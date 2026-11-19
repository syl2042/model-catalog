"""Conservative extractors for documented Markdown tables with exact model IDs."""
import re
import html

OPENAI_URL = 'https://developers.openai.com/api/docs/pricing.md'
ANTHROPIC_URL = 'https://platform.claude.com/docs/en/about-claude/pricing.md'
ANTHROPIC_MODELS_URL = 'https://platform.claude.com/docs/en/models/overview.md'
ANTHROPIC_EFFORT_URL = 'https://platform.claude.com/docs/en/build-with-claude/effort.md'
ANTHROPIC_THINKING_URL = 'https://platform.claude.com/docs/en/build-with-claude/thinking.md'
OPENAI_MODELS_URL = 'https://developers.openai.com/api/docs/models.md'
DEEPSEEK_THINKING_URL = 'https://api-docs.deepseek.com/guides/thinking_mode/'

def markdown(client, url):
    response = client.get(url)
    response.raise_for_status()
    return response.text

def cells(line):
    if not line.strip().startswith('|'): return []
    return [part.strip() for part in line.strip().strip('|').split('|')]

def amount(value):
    # A footnote, range, or other qualification makes the rate ambiguous.
    m = re.fullmatch(r'\$(\d+(?:\.\d+)?)(?:\s*/\s*MTok)?', value.strip())
    return float(m.group(1)) if m else None

def parse_openai(text):
    section = re.search(r'^### Standard pricing data\s*\n(.*?)(?=^### |\Z)', text, re.M | re.S)
    if not section: raise ValueError('OpenAI standard pricing table missing')
    lines = [cells(line) for line in section.group(1).splitlines()]
    header = next((r for r in lines if r and r[0] == 'Model'), None)
    expected = ['Model','Short context input','Short context output','Short context cached input']
    if not header or header[:4] != expected: raise ValueError('OpenAI pricing schema changed')
    result = {}
    for row in lines:
        if len(row) != len(header) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',row[0]): continue
        vals = {}
        for idx, field in [(1,'input'),(2,'output'),(3,'cache_read')]:
            value = amount(row[idx])
            if value is not None: vals['pricing.standard.'+field] = value
        if vals: result[row[0]] = vals
    if not result: raise ValueError('OpenAI pricing table empty')
    return result

def parse_anthropic_models(text):
    # The overview table ties exact API IDs to a model page name by column.
    rows = [cells(line) for line in text.splitlines()]
    modelrow = next((r for r in rows if r and r[0] == 'Model page'),None)
    idrow = next((r for r in rows if r and r[0] == 'Claude API ID'),None)
    if not modelrow or not idrow or len(modelrow) != len(idrow): raise ValueError('Anthropic overview schema changed')
    result = {}
    for name,idcell in zip(modelrow[1:],idrow[1:]):
        n = re.fullmatch(r'\[([^\]]+)\]\(https://platform\.claude\.com/[^)]+\)',name)
        ident = re.fullmatch(r'`([^`]+)`',idcell)
        if n and ident: result[n.group(1)] = ident.group(1)
    if not result: raise ValueError('Anthropic model IDs missing')
    details = {}
    effortrow = next((r for r in rows if r and r[0].startswith('[Default effort]')), None)
    thinkingrow = next((r for r in rows if r and r[0].startswith('[Thinking]')), None)
    for column, idcell in enumerate(idrow[1:], start=1):
        match = re.fullmatch(r'`([^`]+)`', idcell)
        if not match: continue
        values = {}
        if effortrow and len(effortrow) > column:
            effort = re.fullmatch(r'`(low|medium|high|xhigh|max)`', effortrow[column])
            if effort: values['default_effort'] = effort.group(1)
        if thinkingrow and len(thinkingrow) > column:
            thinking = thinkingrow[column]
            if thinking in ('Adaptive', 'Adaptive (always on)'):
                values['adaptive'] = True
                if thinking.endswith('(always on)'): values['can_disable'] = False
        if values: details[match.group(1)] = {'reasoning.by_api.messages.' + k: v for k,v in values.items()}
    return result, details

def parse_anthropic_pricing(text, names):
    section = re.search(r'^## Model pricing\s*\n(.*?)(?=^## |\Z)',text,re.M|re.S)
    if not section: raise ValueError('Anthropic pricing section missing')
    rows = [cells(line) for line in section.group(1).splitlines()]
    expected = ['Model','Base input tokens','5m cache writes','1h cache writes','Cache hits and refreshes','Output tokens']
    if not any(row == expected for row in rows): raise ValueError('Anthropic pricing schema changed')
    result = {}
    for row in rows:
        if len(row) != 6 or row[0] not in names: continue
        values = {}
        for i,field in [(1,'input'),(4,'cache_read'),(5,'output')]:
            price=amount(row[i])
            if price is not None: values['pricing.standard.'+field]=price
        # Cache write prices have explicit duration; do not collapse them into standard.cache_write.
        variants=[]
        for idx,ttl in [(2,300),(3,3600)]:
            price=amount(row[idx])
            if price is not None:
                variants.append({'name':'cache_write','service_tier':'standard','threshold_tokens':None,'cache_ttl_seconds':ttl,
                                 'rates':{'currency':'USD','unit':'per_million_tokens','input':None,'output':None,'cache_read':None,'cache_write':price}})
        result[names[row[0]]] = (values, variants)
    if not result: raise ValueError('Anthropic pricing table empty')
    return result


def parse_anthropic_effort(text, names):
    """Accept only explicit all-five statements tied to documented model names."""
    if '## How effort works' not in text or '## Availability' not in text:
        raise ValueError('Anthropic effort page changed')
    result = {}
    for name, identifier in names.items():
        if re.search(r'(?<![A-Za-z0-9])'+re.escape(name)+r' supports all five effort levels\b', text):
            result[identifier] = {'reasoning.by_api.messages.effort_levels': ['low','medium','high','xhigh','max']}
    return result

def parse_anthropic_thinking(text, names):
    """Use only documented adaptive mode and the page's explicit interleaving rule."""
    if 'Thinking works alongside [tool use]' not in text or 'interleaved thinking is automatic on every model that supports adaptive thinking' not in text:
        raise ValueError('Anthropic thinking rules changed')
    rows = [cells(line) for line in text.splitlines()]
    header = next((r for r in rows if len(r) >= 3 and r[0] == 'Model' and r[2] == '`"adaptive"`'),None)
    if not header: raise ValueError('Anthropic thinking table changed')
    result = {}
    for row in rows:
        if len(row) != len(header) or row[0] not in names or row[2] != 'Adaptive thinking': continue
        result[names[row[0]]] = {
            'reasoning.by_api.messages.compatible_with_tools': True,
            'reasoning.by_api.messages.interleaved_tool_thinking': True,
            'reasoning.by_api.messages.tool_use_conditions': 'Adaptive thinking; forced tool choice depends on the model. Preserve thinking blocks when returning tool results.'}
    return result

def parse_openai_index(text):
    paths = sorted(set(re.findall(r'\]\((/api/docs/models/[a-z0-9.-]+\.md)\)',text)))
    paths = [p for p in paths if p != '/api/docs/models/all.md']
    if not paths or len(paths) > 150: raise ValueError('OpenAI model index changed')
    return paths

def parse_openai_model(text):
    identifier = re.search(r'^Model ID:\s*`([^`]+)`',text,re.M)
    if not identifier: return None
    match = re.search(r'Reasoning\.effort supports:\s*([^\n.]+)\.',text)
    if not match: return None
    pieces = re.sub(r',?\s+and\s+', ', ', match.group(1)).split(',')
    levels=[]; default=None
    for piece in pieces:
        part = re.fullmatch(r'\s*(none|minimal|low|medium|high|xhigh|max)(?:\s*\(default\))?\s*',piece)
        if not part: return None
        levels.append(part.group(1))
        if '(default)' in piece: default=part.group(1)
    values={'reasoning.by_api.responses.effort_levels':levels}
    if default is not None: values['reasoning.by_api.responses.default_effort']=default
    return identifier.group(1), values


def parse_deepseek_thinking(document):
    """Map only models named in a tool-calling + thinking example on this page."""
    section = re.search(r'<h2[^>]*id="tool-calls"[^>]*>(.*?)(?=<h2|</article>)', document, re.S)
    if not section: raise ValueError('DeepSeek tool section missing')
    text = html.unescape(re.sub(r'<[^>]+>', '', section.group(1)))
    if not all(phrase in text for phrase in ('thinking mode supports tool calls', 'multiple turns of reasoning and tool calls', 'reasoning_content', 'must be fully passed back')):
        raise ValueError('DeepSeek tool rules changed')
    ids = set()
    for block in re.findall(r'<pre\b[^>]*>.*?</pre>', section.group(1), re.S):
        snippet = html.unescape(re.sub(r'<[^>]+>', '', block))
        if re.search(r'\btools\s*=\s*tools\b',snippet) and 'thinking' in snippet and 'enabled' in snippet and 'chat.completions.create' in snippet:
            ids.update(re.findall(r"\bmodel\s*=\s*['\"]([A-Za-z0-9._-]+)['\"]",snippet))
    if not ids: raise ValueError('DeepSeek model example missing')
    return {identifier: {
        'reasoning.by_api.chat_completions.compatible_with_tools': True,
        'reasoning.by_api.chat_completions.interleaved_tool_thinking': True,
        'reasoning.by_api.chat_completions.tool_use_conditions': 'Enable thinking and preserve reasoning_content in subsequent requests carrying tools.'
    } for identifier in ids}
