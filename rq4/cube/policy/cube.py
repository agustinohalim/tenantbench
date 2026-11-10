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
