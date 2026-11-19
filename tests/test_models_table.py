import runpy
import pytest

render = runpy.run_path('scripts/generate_models_table.py')['render']

def test_counts_canonical_models_by_creator_and_excludes_unresolved():
    catalog = {'generated_at':'2026-01-01T00:00:00Z', 'checksum_sha256':'a'*64, 'models':{
        'canonical:openai/a':{'grouping':'canonical','canonical_ref':'openai/a','display_name':'A | Model'},
        'canonical:openai/b':{'grouping':'canonical','canonical_ref':'openai/b','display_name':'B'},
        'canonical:other/c':{'grouping':'canonical','canonical_ref':'other/c','display_name':None},
        'unresolved:foo':{'grouping':'unresolved','canonical_ref':None,'display_name':'Uncertain'}}}
    result=render(catalog)
    assert 'Canonical models / Modèles canoniques : **3**' in result
    assert 'Creator namespaces / Espaces de noms créateurs : **2**' in result
    assert 'Unresolved references not counted / Références non résolues non comptées : **1**' in result
    assert '| openai | 2 |' in result
    assert '| openai | A &#124; Model | openai/a |' in result
    assert 'Uncertain' not in result

def test_invalid_canonical_reference_fails():
    with pytest.raises(ValueError):
        render({'generated_at':'x','checksum_sha256':'a'*64,'models':{'x':{'grouping':'canonical','canonical_ref':'unknown','display_name':'X'}}})
