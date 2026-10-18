"""Native actions, with explicit claim-bearing phase contracts.

The ordinary grammar stays identical to the measured latency request. The claim
grammar constrains shape, never truth: strict engine loading and evidence checks
still run on every returned claim. Empty evidence and draft statuses remain valid.
"""
import copy
ACTION_RESPONSE_FORMAT = {
    'type': 'json_schema',
    'json_schema': {'name': 'benchmark_action', 'strict': True, 'schema': {
        'type': 'object', 'properties': {
            'action': {'type': 'string', 'enum': ['shell', 'done', 'draft']},
            'command': {'type': 'string'}, 'summary': {'type': 'string'},
            'completion_asserted': {'type': ['boolean', 'null']},
            'claims': {'type': 'object', 'additionalProperties': True},
            'artifacts': {'type': 'array', 'items': {'type': 'string'}},
        }, 'required': ['action'], 'additionalProperties': False,
    }},
}


def action_response_format(requires_claims=False):
    if not requires_claims:
        return copy.deepcopy(ACTION_RESPONSE_FORMAT)
    strings = {'type': 'array', 'items': {'type': 'string'}}
    fields = {
        'id': {'type': 'string', 'minLength': 1},
        'text': {'type': 'string', 'minLength': 1},
        'kind': {'type': 'string', 'enum': ['observation', 'requirement', 'assumption', 'inference', 'hypothesis', 'decision', 'prediction', 'compliance']},
        'status': {'type': 'string', 'enum': ['draft', 'supported', 'partially_supported', 'unsupported', 'contradicted', 'unverifiable', 'superseded']},
        'stage': {'type': 'string', 'enum': ['created', 'checked', 'explained', 'accepted', 'digested']},
        'boundary': strings, 'depends_on': strings, 'conflicts_with': strings,
        'falsification_tests': strings, 'source_ref': {'type': 'string'},
        'uncertainty': {'type': 'string', 'enum': ['none', 'low', 'medium', 'high', 'insufficient_evidence']},
        'evidence': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': True}},
    }
    bundle = {'type': 'object', 'properties': {
        'schema_version': {'const': '1.0'},
        'claims': {'type': 'array', 'minItems': 1, 'items': {
            'type': 'object', 'properties': fields, 'required': list(fields),
            'additionalProperties': False}},
    }, 'required': ['schema_version', 'claims'], 'additionalProperties': False}
    schema = copy.deepcopy(ACTION_RESPONSE_FORMAT['json_schema']['schema'])
    terminal = copy.deepcopy(schema)
    terminal['properties']['action'] = {'type': 'string', 'enum': ['done', 'draft']}
    terminal['properties']['claims'] = bundle
    terminal['required'] = ['action', 'claims']
    shell = {'type': 'object', 'properties': {
        'action': {'const': 'shell'}, 'command': {'type': 'string', 'minLength': 1}},
        'required': ['action', 'command'], 'additionalProperties': False}
    return {'type': 'json_schema', 'json_schema': {
        'name': 'benchmark_claim_action', 'strict': True,
        'schema': {'oneOf': [shell, terminal]}}}
