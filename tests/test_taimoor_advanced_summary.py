"""Paired summaries must retain the planned composition denominator."""
import numpy as np
import pytest

pytest.importorskip('pandas')
pytest.importorskip('sklearn')

from scripts.summarize_taimoor_advanced import interval,paired_differences


def test_constant_paired_effect_has_exact_interval():
    rows=[{'case_id':str(i),'condition':condition,'x':i+offset}
          for i in range(5) for condition,offset in [('adaptive',0),('learned',2)]]
    result=interval(paired_differences(rows,'adaptive','learned','x',5))
    assert result['mean_difference']==2
    assert result['bootstrap_95_percent_interval']==[2,2]


def test_missing_comparison_case_cannot_be_dropped_for_a_paired_result():
    rows=[{'case_id':'a','condition':'adaptive','x':1},
          {'case_id':'b','condition':'adaptive','x':2},
          {'case_id':'a','condition':'learned','x':1}]
    with pytest.raises(ValueError,match='every planned composition'):
        paired_differences(rows,'adaptive','learned','x',2)


def test_bootstrap_uses_fixed_seed_and_preserves_pairing():
    values=np.array([-1,0,1,2,3],dtype=float)
    assert interval(values)==interval(values.copy())
