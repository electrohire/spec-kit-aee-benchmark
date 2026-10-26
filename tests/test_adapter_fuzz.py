"""Fuzz battery over the upstream adapter's parse paths (Item 5).

The Phase 1 inventory (B-1, entry point 7) catalogued the upstream
adapter's parsing but never fuzzed it: response interpretation is
the adapter's own code around mini-swe-agent's delegated tool-call
parser. This battery feeds malformed, partial and native-format
response variants through `native_usage` and `NativeToolModel.query`
and holds every case to one rule: it either produces a defined
action (a returned message whose single action carries a non-empty
string command) or fails closed with the adapter's named outcome,
`AdmissionError`, latched halted. Any other exception type — a raw
KeyError, TypeError, AttributeError, IndexError or a parser error
escaping unnamed — is a battery failure, as is a silent drop.

The parser behind the boundary is exercised through fixtures in
the style of tests/test_upstream_agent_adapter.py (the real pinned
parser's integration is validated separately, per that file); the
battery varies both the response shapes and the parser's behavior
(junk returns, raised errors), because the adapter's duty at the
boundary is the same either way: nothing unnamed escapes.
"""
import copy
import json
from types import SimpleNamespace

import pytest

from benchmark_runner.upstream_agent_adapter import (
    AdmissionError, Limits, NativeToolModel, native_usage)


def response():
    return dict(model='qwen3.8-27b',
                usage=dict(prompt_tokens=5, completion_tokens=2,
                           total_tokens=7,
                           prompt_tokens_details=dict(cached_tokens=0)),
                choices=[dict(finish_reason='tool_calls',
                              message=dict(
                                  role='assistant',
                                  content='Inspect workspace.',
                                  tool_calls=[dict(
                                      id='one', type='function',
                                      function=dict(
                                          name='bash',
                                          arguments='{"command":"pwd"}'))]))])


class Wire:
    def __init__(self, value):
        self.value = value
        self.generations = 0

    def __call__(self, route, payload, timeout):
        if route == '/slots':
            return [dict(is_processing=False)]
        if route == '/apply-template':
            return dict(prompt='native template includes tools')
        if route == '/tokenize':
            return dict(tokens=[1] * 5)
        assert route == '/v1/chat/completions'
        self.generations += 1
        return copy.deepcopy(self.value)


GOOD_PARSE = (lambda calls, **kw: [dict(
    command=json.loads(c.function.arguments)['command'],
    tool_call_id=c.id) for c in calls])


def model(tmp_path, wire, parse=GOOD_PARSE):
    upstream = SimpleNamespace(
        tool=dict(type='function', function=dict(name='bash')),
        parse=parse,
        observe=lambda **kw: [dict(role='tool', content='fixture')])
    return NativeToolModel(wire, tmp_path / 'calls', upstream, Limits(),
                           'fixture', dict(cohort='adapter_fuzz'))


def assert_defined_action(out):
    actions = out['extra']['actions']
    assert len(actions) == 1
    assert isinstance(actions[0].get('command'), str)
    assert actions[0]['command'].strip()


# ----------------------------------------------------------------
# native_usage: response and usage shapes

@pytest.mark.parametrize('bad_response', [[], 'text', None, 42, True])
def test_usage_response_must_be_an_object(bad_response):
    with pytest.raises(AdmissionError):
        native_usage(bad_response)


@pytest.mark.parametrize('details', ['text', [], 7, None, True])
def test_usage_details_must_be_an_object_when_present(details):
    value = response()['usage']
    value['prompt_tokens_details'] = details
    with pytest.raises(AdmissionError):
        native_usage(dict(usage=value))


@pytest.mark.parametrize('cached', [1.5, True, -1, 6, '0'])
def test_usage_cached_must_be_a_valid_subset(cached):
    value = response()['usage']
    value['prompt_tokens_details'] = dict(cached_tokens=cached)
    with pytest.raises(AdmissionError):
        native_usage(dict(usage=value))


def test_usage_valid_shapes_return_the_usage():
    value = response()['usage']
    assert native_usage(dict(usage=value)) is value
    bare = dict(prompt_tokens=5, completion_tokens=2, total_tokens=7)
    assert native_usage(dict(usage=bare)) is bare
    full_cache = dict(prompt_tokens=5, completion_tokens=2, total_tokens=7,
                      prompt_tokens_details=dict(cached_tokens=5))
    assert native_usage(dict(usage=full_cache)) is full_cache


# ----------------------------------------------------------------
# query: response-shape variants (well-behaved parser)

def mutate(fn):
    value = response()
    fn(value)
    return value


QUERY_CASES = [
    ('response_list', []),
    ('response_text', 'text'),
    ('choices_missing', mutate(lambda v: v.pop('choices'))),
    ('choices_empty', mutate(lambda v: v.update(choices=[]))),
    ('choices_object', mutate(lambda v: v.update(choices={}))),
    ('choice_text', mutate(lambda v: v.update(choices=['x']))),
    ('choice_empty', mutate(lambda v: v.update(choices=[{}]))),
    ('message_missing', mutate(lambda v: v['choices'][0].pop('message'))),
    ('message_text', mutate(lambda v: v['choices'][0].update(message='x'))),
    ('tool_calls_one_char', mutate(
        lambda v: v['choices'][0]['message'].update(tool_calls='a'))),
    ('tool_call_empty', mutate(
        lambda v: v['choices'][0]['message'].update(tool_calls=[{}]))),
    ('tool_call_no_function', mutate(
        lambda v: v['choices'][0]['message'].update(
            tool_calls=[dict(id='one')]))),
    ('tool_call_function_text', mutate(
        lambda v: v['choices'][0]['message'].update(
            tool_calls=[dict(id='one', function='bash')]))),
    ('function_empty', mutate(
        lambda v: v['choices'][0]['message'].update(
            tool_calls=[dict(id='one', function={})]))),
    ('function_no_arguments', mutate(
        lambda v: v['choices'][0]['message']['tool_calls'][0].update(
            function=dict(name='bash')))),
    ('arguments_int', mutate(
        lambda v: v['choices'][0]['message']['tool_calls'][0].update(
            function=dict(name='bash', arguments=42)))),
    ('arguments_not_json', mutate(
        lambda v: v['choices'][0]['message']['tool_calls'][0].update(
            function=dict(name='bash', arguments='not json')))),
    ('arguments_no_command', mutate(
        lambda v: v['choices'][0]['message']['tool_calls'][0].update(
            function=dict(name='bash', arguments='{"other": 1}')))),
]


@pytest.mark.parametrize('value', [v for _name, v in QUERY_CASES],
                         ids=[name for name, _v in QUERY_CASES])
def test_query_malformed_responses_fail_closed_named(tmp_path, value):
    m = model(tmp_path, Wire(value))
    with pytest.raises(AdmissionError):
        m.query([dict(role='user', content='public task')])
    assert m.halted


def test_query_canonical_response_is_a_defined_action(tmp_path):
    m = model(tmp_path, Wire(response()))
    assert_defined_action(m.query([dict(role='user', content='task')]))


@pytest.mark.parametrize('arguments', ['{"command": 42}',
                                       '{"command": ""}',
                                       '{"command": "   "}'])
def test_query_non_string_or_empty_commands_fail_closed(tmp_path, arguments):
    value = response()
    value['choices'][0]['message']['tool_calls'][0]['function'][
        'arguments'] = arguments
    m = model(tmp_path, Wire(value))
    with pytest.raises(AdmissionError):
        m.query([dict(role='user', content='task')])
    assert m.halted


# ----------------------------------------------------------------
# query: parser-behavior variants (canonical response)

def raising_parse(exc):
    def parse(calls, **kw):
        raise exc
    return parse


PARSER_CASES = [
    ('parse_returns_none', lambda calls, **kw: None),
    ('parse_returns_empty', lambda calls, **kw: []),
    ('parse_returns_two', lambda calls, **kw: [dict(command='a'),
                                               dict(command='b')]),
    ('parse_returns_no_command', lambda calls, **kw: [dict(other=1)]),
    ('parse_returns_int_command', lambda calls, **kw: [dict(command=42)]),
    ('parse_raises_runtime', raising_parse(RuntimeError('parser boom'))),
    ('parse_raises_value', raising_parse(ValueError('bad format'))),
    ('parse_raises_key', raising_parse(KeyError('command'))),
]


@pytest.mark.parametrize('parse', [p for _n, p in PARSER_CASES],
                         ids=[n for n, _p in PARSER_CASES])
def test_query_parser_outcomes_fail_closed_named(tmp_path, parse):
    m = model(tmp_path, Wire(response()), parse=parse)
    with pytest.raises(AdmissionError):
        m.query([dict(role='user', content='task')])
    assert m.halted
