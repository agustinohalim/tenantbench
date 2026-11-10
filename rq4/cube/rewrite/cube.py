from cube import config

PASSWORD = "rq4"


@config('check_sql_auth')
def check_sql_auth(req: dict, user_name: str, password: str) -> dict:
    if password and password != PASSWORD:
        raise Exception('Access denied')
    if user_name in ('t1', 't2', 't3', 't4'):
        ctx = {'tenant': int(user_name[1]), 'groups': ['tenant']}
    elif user_name == 'noclaim':
        ctx = {'groups': ['tenant']}
    elif user_name == 'nogroup':
        ctx = {}
    else:
        raise Exception('Access denied')
    return {'password': password or PASSWORD, 'securityContext': ctx}


@config('context_to_groups')
def context_to_groups(ctx: dict) -> list[str]:
    # documented default: ctx['securityContext'].get('groups', ['default'])
    return ctx['securityContext'].get('groups', ['default'])


CUBES = ('loan', 'account', 'trans')


@config('query_rewrite')
def query_rewrite(query: dict, ctx: dict) -> dict:
    # Documented pattern (docs.cube.dev access-control/context, "Using query_rewrite"):
    # add the filter only when the claim is present. Generalised to every cube the query touches.
    if 'tenant' in ctx['securityContext']:
        # Deviation P4: SQL API pushdown sends member expressions as dicts with 'cubeName'.
        def cube_of(m):
            if isinstance(m, dict):
                return m.get('cubeName') or str(m.get('member', '')).split('.')[0]
            return str(m).split('.')[0]
        members = [m for k in ('measures', 'dimensions', 'segments') for m in query.get(k, [])]
        members += [f for f in query.get('filters', []) if isinstance(f, dict) and 'member' in f]
        members += [t.get('dimension', '') for t in query.get('timeDimensions', [])]
        for c in sorted({cube_of(m) for m in members if m} & set(CUBES)):
            query['filters'].append({'member': f'{c}.tenant_id', 'operator': 'equals',
                                     'values': [str(ctx['securityContext']['tenant'])]})
    return query
