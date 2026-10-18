"""One native action grammar for every treatment; no prose/tool-tag extraction."""
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
