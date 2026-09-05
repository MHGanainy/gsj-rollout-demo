"""CP-86: real frozen captures and explicitly synthetic projection fixtures."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / 'tests/fixtures'

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

reader = module('read')
bootstrap = module('bootstrap')

def body(name):
    return json.loads((F / name).read_text())

def export(name, capsys):
    reader.cmd_export(SimpleNamespace(dir=F, id=Path(name).stem.removesuffix(".thinking-off"), arrays=False))
    return json.loads(capsys.readouterr().out)

def show(name, capsys):
    reader.cmd_show(SimpleNamespace(dir=F, id=Path(name).stem.removesuffix(".thinking-off"), full=True, tokenizer=None))
    return capsys.readouterr().out

def test_reordered_identity(capsys):
    name='synthetic-reordered.json'
    trace=reader.trace_of(body(name))
    ctx=reader.decision_context(trace)
    assert ctx['hits'] == 1
    assert reader.session_citations(trace,ctx)[0][1] is True
    out=export(name,capsys)
    assert out['decision_census']['hits_returned'] == 1
    assert out['decision_census']['tokens_written'][0]['grounded'] is True
    result=next(r for r in out['turns'][0]['results'] if r['tool_call_id']=='dec1')
    assert result['name']=='mcp_gsj_search_decisions'
    text=show(name,capsys)
    assert '1 decision hit(s)' in text and 'UNGROUNDED' not in text

def test_missing_and_unmatched_named(capsys):
    name='synthetic-missing-result.json'
    out=export(name,capsys)
    assert out['decision_census']['searched'] is True
    assert out['decision_census']['hits_returned']==0
    results=[r for t in out['turns'] for r in t['results']]
    assert any(r['tool_call_id']=='dec1' and r['status']=='missing' for r in results)
    assert any(r['tool_call_id']=='orphan' and r['status']=='unmatched' for r in results)
    text=show(name,capsys)
    assert 'missing result' in text and 'dec1' in text
    assert 'unmatched result' in text and 'orphan' in text

def test_failed_write(capsys):
    out=export('synthetic-failed-write.json',capsys)
    d=out['deliverable']
    assert d['written'] is False and d['attempted'] is True
    assert d['outcome']=='failed'
    assert d['content']=='No file was actually written.'
    text=show('synthetic-failed-write.json',capsys)
    assert 'failed' in text and 'written at turn' not in text

@pytest.mark.parametrize('content,expected',[(None,'unknown'),('opaque','unknown'),('Successfully wrote 12 bytes to /tmp/x','succeeded'),('EACCES: permission denied','failed')])
def test_write_outcomes(content,expected):
    trace=reader.trace_of(body('synthetic-failed-write.json'))
    if content is None: trace['response_messages'].pop(1)
    else: trace['response_messages'][1]['content']=content
    assert reader.find_deliverable(trace)['outcome']==expected

@pytest.mark.parametrize('raw',[[],42,None,{'findings': [], 'session_result': []},{'trajectory': []},{'trajectory': {'traces': [42]}}])
def test_archive_shape(tmp_path,capsys,raw):
    p=tmp_path/'bad.json';p.write_text(json.dumps(raw))
    with pytest.raises(SystemExit): reader.load({'path':p})
    err=capsys.readouterr().err
    assert str(p) in err and 'expected' in err.lower() and 'restore' in err.lower()

@pytest.mark.parametrize('raw',['42','[]','false','null'])
def test_config_shape(tmp_path,capsys,raw):
    p=tmp_path/'bad.yaml';p.write_text(raw)
    with pytest.raises(SystemExit): bootstrap.load_demo_config(p)
    err=capsys.readouterr().err
    assert str(p) in err and 'mapping' in err and 'config.yaml.example' in err

@pytest.mark.parametrize('fixture',json.loads((F/'manifest.json').read_text()),ids=lambda f:f['file'][:26])
def test_real_capture(fixture,capsys):
    import hashlib
    assert hashlib.sha256((F/fixture['file']).read_bytes()).hexdigest()==fixture['sha256']
    out=export(fixture['file'],capsys); census=out['decision_census']
    assert census['hits_returned']==fixture['hits']
    assert len(census['tokens_written'])==fixture['tokens']
    assert sum(t['grounded'] for t in census['tokens_written'])==0
    text=show(fixture['file'],capsys)
    if fixture['tokens']: assert 'UNGROUNDED rn' in text and 'dec:GREV000082013:rn:7' in text
    else: assert 'NONE' in text and '5 decision hit(s) available' in text

def test_legacy_concatenated_results():
    parsed=reader.parse_decisions('{"decision_id":"GREV000082013"}\n{"decision_id":"GREV000092013"}')
    assert parsed[0] is None and len(parsed[1])==2


def test_duplicate_result_ids_are_ambiguous():
    trace=reader.trace_of(body('synthetic-reordered.json'))
    trace['response_messages'].insert(2,copy.deepcopy(trace['response_messages'][1]))
    ctx=reader.decision_context(trace)
    assert ctx['hits']==0
    events=[e for t in reader.turns_of(trace) for e in t['tools'] if e['id']=='dec1']
    assert len(events)==3 and all(e['status']=='ambiguous' for e in events)


def test_result_after_later_turn_not_available_early():
    trace=reader.trace_of(body('synthetic-reordered.json'))
    result=trace['response_messages'].pop(1)
    trace['response_messages'].append({'role':'assistant','content':'later'})
    trace['response_messages'].append(result)
    ctx=reader.decision_context(trace)
    assert ctx['hits']==1
    assert reader.session_citations(trace,ctx)[0][1] is False


def test_result_without_any_assistant_is_retained():
    trace={'response_messages':[{'role':'tool','tool_call_id':'orphan','content':'evidence'}]}
    blocks=reader.turn_blocks(trace,[],None,True,None,{})
    assert any('unmatched result: orphan' in line for _,lines in blocks for line in lines)


def test_explicit_error_overrides_success_text():
    trace=reader.trace_of(body('synthetic-failed-write.json'))
    trace['response_messages'][1].update(content='Successfully wrote 12 bytes to /tmp/x',isError=True)
    assert reader.find_deliverable(trace)['written'] is False


def test_error_result_is_not_retrieval_evidence():
    trace=reader.trace_of(body('synthetic-reordered.json'))
    trace['response_messages'][1]['isError']=True
    assert reader.decision_context(trace)['hits']==0
    blocks=reader.turn_blocks(trace,[None,None],None,True,None,{})
    text='\n'.join(line for _,lines in blocks for line in lines)
    assert 'failed result: dec1' in text and 'decision hit(s)' not in text


def test_success_path_with_error_word_is_not_an_error():
    trace=reader.trace_of(body('synthetic-failed-write.json'))
    trace['response_messages'][1]['content']='Successfully wrote 12 bytes to /tmp/EACCES-permission denied'
    assert reader.find_deliverable(trace)['outcome']=='succeeded'
