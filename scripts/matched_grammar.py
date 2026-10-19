"""Fixed bounded GBNF contracts for the pinned local decoder.

llama.cpp d344123fe silently makes repetitions above2000 unbounded. Every
repetition here stays below that threshold; the policy capacity remains3000.
JSON Schema is still checked independently after decoding. Fixed key order is
transport serialization, not treatment-specific semantic guidance.
"""
import json

DOC_SCHEMA = dict(type='object', properties=dict(document=dict(type='string', minLength=1, maxLength=3000)),
                  required=['document'], additionalProperties=False)
DECISION_SCHEMA = dict(type='object', properties=dict(
    verdict=dict(type='string', enum=['hallucinated', 'grounded', 'abstain']),
    rationale=dict(type='string', maxLength=320),
    source_quotes=dict(type='array', items=dict(type='string', minLength=1, maxLength=120), maxItems=2),
    uncertainties=dict(type='array', items=dict(type='string', minLength=1, maxLength=80), maxItems=3)),
    required=['verdict', 'rationale', 'source_quotes', 'uncertainties'], additionalProperties=False)
COMMON = r'''ws ::= [ \t\n\r]{0,16}
jchar ::= [^"\\\x7F\x00-\x1F] | "\\" (["\\bfnrt/] | "u" [0-9a-fA-F]{4})
'''
DOCUMENT = r'''root ::= "{" ws "\"document\"" ws ":" ws document ws "}" ws
document ::= "\"" full-block{0,29} tail "\""
full-block ::= jchar{100}
tail ::= jchar{1,100}
'''
DECISION = r'''root ::= "{" ws "\"verdict\"" ws ":" ws verdict ws "," ws "\"rationale\"" ws ":" ws rationale ws "," ws "\"source_quotes\"" ws ":" ws quotes ws "," ws "\"uncertainties\"" ws ":" ws uncertainties ws "}" ws
verdict ::= "\"grounded\"" | "\"hallucinated\"" | "\"abstain\""
rationale ::= "\"" jchar{0,320} "\""
quote ::= "\"" jchar{1,120} "\""
uncertainty ::= "\"" jchar{1,80} "\""
quotes ::= "[" ws (quote (ws "," ws quote){0,1})? ws "]"
uncertainties ::= "[" ws (uncertainty (ws "," ws uncertainty){0,2})? ws "]"
'''


def grammar_for(kind):
    if kind not in ('document', 'decision'):
        raise ValueError('unknown registered decoder contract')
    return (DOCUMENT if kind == 'document' else DECISION) + COMMON


def native_probe_contracts():
    exact = {**DOC_SCHEMA, 'properties': {'document': dict(type='string', minLength=3000, maxLength=3000)}}
    sentinel = 'decoder-only cobalt: "q"\nbackslash \\; snowman \u2603'
    const = {**DOC_SCHEMA, 'properties': {'document': dict(type='string', const=sentinel)}}
    return [dict(schema=exact, output=1536, instruction='Return document containing exactly3000 lowercase x characters; no other document characters. The decoder enforces the contract.'),
            dict(schema=DECISION_SCHEMA, output=1024, instruction='Source: Only cobalt is registered. Candidate: Amber is registered. Give a JSON decision with rationale, source_quotes and uncertainties. Aim for4000 rationale characters but obey the decoder. This is technical delivery, no factual correctness gate.'),
            dict(schema=const, output=1536, instruction='Return a JSON document. The decoder alone supplies a fixed synthetic literal including escaping and Unicode; do not infer factual truth or human acceptance.')]


def schema_grammar(schema, *, probe=False):
    if schema == DOC_SCHEMA:
        return grammar_for('document')
    if schema == DECISION_SCHEMA:
        return grammar_for('decision')
    if probe:
        contracts = native_probe_contracts()
        if schema == contracts[0]['schema']:
            return grammar_for('document').replace('full-block{0,29}', 'full-block{29}').replace('jchar{1,100}', 'jchar{100}')
        if schema == contracts[2]['schema']:
            # A GBNF literal whose contents are the complete JSON string token.
            literal = json.dumps(json.dumps(schema['properties']['document']['const'], ensure_ascii=True))
            return 'root ::= "{" ws "\\\"document\\\"" ws ":" ws ' + literal + ' ws "}" ws\n' + COMMON
    raise ValueError('unregistered native schema; refuse inferred or weaker grammar')


def receipt_schema(call, plan):
    request = call['request']
    if plan.get('decoder_contract') != 'bounded-gbnf-split-v1':
        return request['response_format']['json_schema']['schema']
    schema = call.get('validation_schema')
    if not isinstance(schema, dict) or 'response_format' in request or 'json_schema' in request:
        raise ValueError('missing independent schema or competing decoder format')
    if request.get('grammar') != schema_grammar(schema):
        raise ValueError('registered bounded grammar missing/changed')
    return schema
