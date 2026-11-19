import json
from pathlib import Path
import pytest
from aurora_model_catalog.catalog import merge_variants
from aurora_model_catalog.normalization import blank
from aurora_model_catalog.sources.official_docs import parse_openai, parse_anthropic_models, parse_anthropic_pricing

OPENAI = '''### Standard pricing data
| Model | Short context input | Short context output | Short context cached input |
| --- | --- | --- | --- |
| exact-model | $2 | $10 | $0.2 |
### Batch pricing data
| exact-model | $1 | $5 | $0.1 |
'''
OVERVIEW = '''| Model page | [Claude Example](https://platform.claude.com/docs/en/models/example) |
| Claude API ID | `exact-claude` |
| [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking) | Adaptive (always on) |
| [Default effort](https://platform.claude.com/docs/en/build-with-claude/effort) | `high` |
'''
PRICING = '''## Model pricing
| Model | Base input tokens | 5m cache writes | 1h cache writes | Cache hits and refreshes | Output tokens |
| --- | --- | --- | --- | --- | --- |
| Claude Example | $3 / MTok | $4 / MTok | $6 / MTok | $0.30 / MTok<sup>1</sup> | $15 / MTok |
## Other pricing
'''

def test_standard_pricing_excludes_batch():
    values=parse_openai(OPENAI)['exact-model']
    assert values['pricing.standard.input']==2
    assert values['pricing.standard.output']==10
    with pytest.raises(ValueError): parse_openai(OPENAI.replace('Standard pricing data','Other pricing'))

def test_anthropic_explicit_mapping_scope_and_footnote():
    names, details=parse_anthropic_models(OVERVIEW)
    assert names=={'Claude Example':'exact-claude'}
    assert details['exact-claude']=={'reasoning.by_api.messages.default_effort':'high','reasoning.by_api.messages.adaptive':True,'reasoning.by_api.messages.can_disable':False}
    values, variants=parse_anthropic_pricing(PRICING,names)['exact-claude']
    assert values['pricing.standard.input']==3
    assert 'pricing.standard.cache_read' not in values
    assert [v['cache_ttl_seconds'] for v in variants]==[300,3600]
    assert variants[1]['rates']['cache_write']==6
    assert not parse_anthropic_pricing(PRICING,{'Claude Example':'other'})['other'][0].get('pricing.standard.cache_read')

def test_variants_keep_independent_provenance_and_priority():
    def variant(name, ttl, price):
        return {'name':name,'service_tier':'standard','threshold_tokens':None,'cache_ttl_seconds':ttl,'rates':{'currency':'USD','unit':'per_million_tokens','input':None,'output':None,'cache_read':None,'cache_write':price}}
    official={'url':'https://example.com/docs','source_type':'official_docs','observed_at':'2026-01-01T00:00:00Z','published_at':None}
    community={**official,'source_type':'litellm'}
    m=blank('anthropic','x'); conflicts=[]
    merge_variants(m,[variant('cache_write',300,4)],official,conflicts)
    merge_variants(m,[variant('cache_write',300,5),variant('cache_write',3600,8)],community,conflicts)
    assert [v['rates']['cache_write'] for v in m['pricing']['variants']]==[4,8]
    assert len(conflicts)==1
    assert m['provenance']['pricing.variants.0']['source_type']=='official_docs'
    assert m['provenance']['pricing.variants.1']['source_type']=='litellm'

def test_published_schema_matches_code():
    from aurora_model_catalog.schema import Catalog
    assert json.loads(Path('schema/model-catalog.v1.schema.json').read_text())==Catalog.model_json_schema()

def test_catalog_rejects_missing_provenance(tmp_path):
    from aurora_model_catalog import catalog
    from test_catalog import fake_client
    data=catalog.sync(tmp_path/'catalog.json',client=fake_client(),env={})
    data['models']['openai:alpha']['provenance'].pop('identity.display_name')
    with pytest.raises(ValueError,match='missing provenance'): catalog.validate(data)


def test_openai_scoped_effort_from_explicit_page():
    from aurora_model_catalog.sources.official_docs import parse_openai_model
    result=parse_openai_model('Model ID: `model-x`\nReasoning.effort supports: none, low, medium (default), high, and xhigh.\n')
    assert result == ('model-x', {'reasoning.by_api.responses.effort_levels':['none','low','medium','high','xhigh'], 'reasoning.by_api.responses.default_effort':'medium'})
    assert parse_openai_model('Model ID: `model-x`\nSome efforts may be supported.') is None

def test_anthropic_effort_and_tools_depend_on_explicit_docs():
    from aurora_model_catalog.sources.official_docs import parse_anthropic_effort, parse_anthropic_thinking
    names={'Claude Example':'exact-claude'}
    effort='## How effort works\nClaude Example supports all five effort levels.\n## Availability'
    assert parse_anthropic_effort(effort,names)['exact-claude']['reasoning.by_api.messages.effort_levels']==['low','medium','high','xhigh','max']
    thinking='''Thinking works alongside [tool use]
With adaptive thinking, interleaved thinking is automatic on every model that supports adaptive thinking.
| Model | No `thinking` field | `"adaptive"` | `"enabled"` |
| Claude Example | Thinking off | Adaptive thinking | 400 error |
'''
    values=parse_anthropic_thinking(thinking,names)['exact-claude']
    assert values['reasoning.by_api.messages.compatible_with_tools'] is True
    assert values['reasoning.by_api.messages.interleaved_tool_thinking'] is True
    with pytest.raises(ValueError): parse_anthropic_thinking(thinking.replace('Thinking works alongside','Unclear relationship'),names)

def test_community_effort_requires_explicit_list():
    from aurora_model_catalog.normalization import models_dev_values
    assert models_dev_values({'reasoning_options':[{'type':'effort','values':['low','high']}]})['reasoning.effort_levels']==['low','high']
    assert 'reasoning.effort_levels' not in models_dev_values({'reasoning':True})
    assert 'reasoning.effort_levels' not in models_dev_values({'reasoning_options':[{'type':'effort','values':['low',3]}]})

def test_scoped_provenance_merge_retains_other_properties():
    from aurora_model_catalog.normalization import apply, blank, expand_scoped_provenance
    m=blank('anthropic','model-x')
    src={'url':'https://example.com','source_type':'official_docs','observed_at':'2026-01-01T00:00:00Z','published_at':None}
    apply(m,{'reasoning.by_api.messages':{'default_effort':'high'}},src,[])
    expand_scoped_provenance({'anthropic:model-x':m})
    apply(m,{'reasoning.by_api.messages.effort_levels':['low','high']},src,[])
    assert m['reasoning']['by_api']['messages']=={'default_effort':'high','effort_levels':['low','high']}
    assert 'reasoning.by_api.messages.default_effort' in m['provenance']
    assert 'reasoning.by_api.messages.effort_levels' in m['provenance']

def test_deepseek_requires_explicit_scoped_tool_example():
    from aurora_model_catalog.sources.official_docs import parse_deepseek_thinking
    text='''<h2 id="tool-calls">Tool Calls</h2>
    <p>The DeepSeek model&#x27;s thinking mode supports tool calls. It performs multiple turns of reasoning and tool calls. The reasoning_content must be fully passed back.</p>
    <pre>client.chat.completions.create(model='deepseek-flash', tools=tools, thinking='enabled')</pre>
    <h2>Other</h2>'''
    values=parse_deepseek_thinking(text)['deepseek-flash']
    assert values['reasoning.by_api.chat_completions.compatible_with_tools'] is True
    assert values['reasoning.by_api.chat_completions.interleaved_tool_thinking'] is True
    with pytest.raises(ValueError): parse_deepseek_thinking(text.replace('tools=tools','tools=None'))
