#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from pathlib import Path
from urllib import request, error, parse
from datetime import datetime, timezone

ENV_FILES = [Path('/workspace/.hermes/.env'), Path('/home/glameAI/.hermes/.env')]

def load_dotenv():
    for p in ENV_FILES:
        if p.exists():
            for raw in p.read_text(encoding='utf-8').splitlines():
                line=raw.strip()
                if not line or line.startswith('#') or '=' not in line: continue
                k,v=line.split('=',1); k=k.strip(); v=v.strip().strip('"').strip("'")
                os.environ.setdefault(k,v)
            return

def build_url(path):
    return os.environ['GLAME_API_BASE_URL'].rstrip('/') + '/' + path.lstrip('/')

def login():
    token=os.environ.get('GLAME_API_TOKEN','').strip()
    if token: return token
    body=parse.urlencode({'username': os.environ['GLAME_AUTH_USERNAME'], 'password': os.environ['GLAME_AUTH_PASSWORD']}).encode()
    req=request.Request(build_url('/api/auth/login'), data=body, method='POST', headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'})
    with request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())['access_token']

def api(method, path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req=request.Request(build_url(path), data=data, method=method, headers={
        'Accept':'application/json', 'Authorization': f'Bearer {TOKEN}', 'User-Agent':'glame-hermes-agent/0.1',
        **({'Content-Type':'application/json'} if payload is not None else {})
    })
    try:
        with request.urlopen(req, timeout=60) as r:
            text=r.read().decode('utf-8')
            return r.status, json.loads(text) if text else None
    except error.HTTPError as e:
        body=e.read().decode('utf-8','replace')
        raise RuntimeError(f'{method} {path} -> HTTP {e.code}: {body[:1000]}')

def delta(new, old):
    out={}
    if isinstance(new, dict) and isinstance(old, dict):
        for section, vals in new.items():
            if isinstance(vals, dict):
                sec={}
                for k,v in vals.items():
                    ov=(old.get(section) or {}).get(k)
                    if isinstance(v,(int,float)) and isinstance(ov,(int,float)):
                        if abs(float(v)-float(ov)) > 1e-9:
                            sec[k]={'old': ov, 'new': v, 'delta': v-ov}
                    elif v != ov:
                        sec[k]={'old': ov, 'new': v}
                if sec: out[section]=sec
    return out

load_dotenv()
TOKEN=login()
now=datetime.now(timezone.utc).isoformat()
_, board=api('GET','/api/ai-marketer/boards/product')
_, focus=api('GET','/api/agent-interactions/tasks/82dcbc2c-386e-43dd-881c-7604a855b87b')
_, admin=api('GET','/api/agent-interactions/tasks/4c66355e-32d8-4f7f-b85f-f64e0c2ca48a')
_, inventory=api('GET','/api/inventory/dashboard')
_, product_summary=api('GET','/api/director/data/product-summary')
_, top_sellers=api('GET','/api/analytics/products/top-sellers')
_, slow_movers=api('GET','/api/analytics/products/slow-movers')

prev_inv=(focus.get('task_context') or {}).get('inventory_snapshot') or {}
changes=delta(inventory, prev_inv)
brief_changes=[]
for section, fields in changes.items():
    for k,v in fields.items():
        if 'delta' in v:
            brief_changes.append(f"{section}.{k}: {v['old']} → {v['new']} ({v['delta']:+g})")
        else:
            brief_changes.append(f"{section}.{k}: {v['old']} → {v['new']}")

refresh={
    'refreshed_at': now,
    'source': 'Hermes kanban t_ae0795a9',
    'live_endpoints': [
        '/api/ai-marketer/boards/product', '/api/inventory/dashboard', '/api/director/data/product-summary',
        '/api/analytics/products/top-sellers', '/api/analytics/products/slow-movers'
    ],
    'board_stats': board.get('stats'),
    'changed_fields': changes,
    'summary': {
        'board_total_tasks': (board.get('stats') or {}).get('total'),
        'board_active_tasks': (board.get('stats') or {}).get('active'),
        'board_approvals': (board.get('stats') or {}).get('approvals'),
        'top_sellers_count': len(top_sellers.get('products') or []),
        'slow_movers_count': len(slow_movers.get('slow_movers') or []),
        'total_active_products': product_summary.get('total_active_products'),
        'core_assortment': product_summary.get('core_assortment'),
    },
    'next_step': 'Запустить/доработать задачу product focus 82dcbc2c-386e-43dd-881c-7604a855b87b (Kanban t_dd8d52cd) на свежем snapshot: список продвигать/дозаказать/распродать/исключить.',
}
# Patch the existing product focus board task with fresh snapshots and change log.
focus_ctx=dict(focus.get('task_context') or {})
focus_ctx['inventory_snapshot_previous']=prev_inv
focus_ctx['inventory_snapshot']=inventory
focus_ctx['product_summary_snapshot']=product_summary
focus_ctx['last_data_refresh']=refresh
focus_ctx['data_refresh_history']=(focus_ctx.get('data_refresh_history') or [])[-9:] + [refresh]
status, patched_focus=api('PATCH','/api/agent-interactions/tasks/82dcbc2c-386e-43dd-881c-7604a855b87b', {'task_context': focus_ctx})
# Patch admin task context with execution record; keep platform status pending_approval per workflow.
admin_ctx=dict(admin.get('task_context') or {})
admin_ctx['last_assortment_board_refresh']=refresh
status2, patched_admin=api('PATCH','/api/agent-interactions/tasks/4c66355e-32d8-4f7f-b85f-f64e0c2ca48a', {'task_context': admin_ctx})
message=(
    'AI Assortment: данные product-доски обновлены. '\
    f"На доске product сейчас задач: total={refresh['summary']['board_total_tasks']}, active={refresh['summary']['board_active_tasks']}, approvals={refresh['summary']['board_approvals']}. "
    'Обновлен inventory_snapshot в задаче «Подготовить продуктовый фокус» и добавлен last_data_refresh/change_log. '
    'Ключевые изменения: ' + ('; '.join(brief_changes[:14]) if brief_changes else 'изменений относительно прежнего inventory_snapshot не найдено') + '. '
    'Следующий шаг: после подтверждения директора выполнить product focus по свежему snapshot и выдать список товарных решений: продвигать / дозаказать / распродать / исключить из кампаний.'
)
status3, log=api('POST','/api/agent-interactions/tasks/4c66355e-32d8-4f7f-b85f-f64e0c2ca48a/dialog-logs', {
    'role': 'assortment-agent',
    'message': message,
    'metadata': {'kind':'assistant_reply','source':'Hermes Kanban t_ae0795a9','refresh': refresh}
})
print(json.dumps({
    'refreshed_at': now,
    'product_board_stats': board.get('stats'),
    'focus_task_id': patched_focus['id'],
    'admin_task_id': patched_admin['id'],
    'admin_task_status': patched_admin['status'],
    'dialog_log_id': log.get('log_id'),
    'change_count': sum(len(v) for v in changes.values()),
    'brief_changes': brief_changes,
    'refresh_summary': refresh['summary'],
    'next_step': refresh['next_step'],
    'message': message,
}, ensure_ascii=False, indent=2))
