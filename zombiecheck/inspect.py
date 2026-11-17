"""Optional, bounded, checkpointed inspection of one exact public intake."""
import json
import os
import uuid
from urllib.parse import urlparse
from .models import safe_url, utcnow
from .tinyfish import APIError


def inspect_intake(engine,audit_id,row_id,method='browser',run_id=None):
    token=str(uuid.uuid4())
    if not engine.store.claim_worker(audit_id,token,os.getpid()):
        raise ValueError('Another worker owns this audit. Finish or pause it before inspecting intake.')
    try:
        return _inspect_intake(engine,audit_id,row_id,method,run_id)
    finally:
        engine.store.release_worker(audit_id,token)


def _inspect_intake(engine,audit_id,row_id,method='browser',run_id=None):
    if method not in ('browser','agent'):
        raise ValueError('Inspection method must be browser or agent')
    store=engine.store
    row=next((r for r in store.rows(audit_id) if r['row_id']==row_id),None)
    if row is None:
        raise ValueError('Unknown input row ID')
    result=row.get('result') or {}
    identity=result.get('identity') or {}
    if not identity.get('verified') or identity.get('status') not in ('same','rebranded','acquired_continues'):
        raise ValueError('First verify the original entity/posting identity before inspecting intake')
    url=safe_url(identity.get('canonical_url'))
    if not url:
        raise ValueError('No verified public intake URL')
    if result.get('employer_name'):
        from .jobs import _url_identity
        expected_id=(row.get('raw') or {}).get('posting_id','')
        matches=lambda final:_url_identity(final,expected_id)==_url_identity(url,expected_id)
    else:
        expected_id=''
        url=safe_url((result.get('signals') or {}).get('signup',{}).get('url')) or url
        matches=lambda final:urlparse(final).hostname==urlparse(url).hostname
    inspections=result.setdefault('intake_inspections',{})
    state=inspections.setdefault(method,{})
    if state.get('status')=='complete':
        return state
    client=engine.client_factory(audit_id)
    if method=='agent':
        run_id=run_id or state.get('run_id')
        if not run_id:
            if state.get('status') in ('creating','uncertain'):
                raise ValueError('Previous run creation outcome is uncertain. Supply its run ID; no duplicate paid run was started.')
            if not store.reserve_request(audit_id,0.096):
                raise APIError(402,'Inspection would exceed the audit spending cap')
            state.update(status='creating',url=url,checked_at=utcnow(),reserved_usd=0.096)
            store.row_update(audit_id,row_id,result=result)
            try:
                queued=client.queue_intake_inspection(url,result.get('current_job_title') or row['name'],expected_id)
                run_id=queued.get('run_id')
                if not run_id:
                    raise APIError(0,'Agent did not return a run ID',ambiguous=True)
            except APIError as error:
                state.update(status='uncertain' if error.ambiguous else 'failed',error=str(error))
                if not error.ambiguous:
                    store.refund_request(audit_id,0.096)
                store.row_update(audit_id,row_id,result=result)
                raise
            state.update(status='running',run_id=run_id)
            store.row_update(audit_id,row_id,result=result)
        run=client.agent_run(run_id)
        state.update(run_id=run_id,remote_status=run.get('status'),checked_at=run.get('finished_at') or utcnow())
        if run.get('status') not in ('COMPLETED','FAILED','CANCELLED','TIMED_OUT'):
            state['status']='running'
            store.row_update(audit_id,row_id,result=result)
            return state
        observed=run.get('result') or {}
        if not isinstance(observed,dict):observed={}
        state.update(actual_steps=run.get('num_of_steps'),run_url='https://agent.tinyfish.ai/runs/'+run_id,
                     observation=observed,error=run.get('error'))
        visible=observed.get('application_form_visible') is True and bool(observed.get('application_fields'))
        verified=run.get('status')=='COMPLETED' and visible and matches(safe_url(observed.get('final_url')))
        if expected_id:
            verified=verified and str(observed.get('posting_id'))==expected_id
    else:
        if state.get('status')=='creating':
            raise ValueError('Previous browser creation outcome is uncertain; inspect the saved session before retrying')
        if not store.reserve_request(audit_id,0.10):
            raise APIError(402,'Inspection would exceed the audit spending cap')
        state.update(status='creating',url=url,checked_at=utcnow(),reserved_usd=0.10)
        store.row_update(audit_id,row_id,result=result)
        try:
            observed=client.browser_signup(url)
        except Exception as error:
            state.update(status='uncertain',error=str(error))
            store.row_update(audit_id,row_id,result=result)
            raise
        state.update(observation=observed)
        verified=observed.get('verified') is True and matches(safe_url(observed.get('final_url')))
    state.update(status='complete',verified=bool(verified),url=url,
        note=('Exact public intake controls observed. No form submitted; backend acceptance and genuine vacancy intent are unverified.'
              if verified else 'The exact public entry was visited; role-specific intake controls were not established. No form submitted.'))
    if verified:
        signal=result['signals']['signup']
        signal.update(verified=True,status='active',method='tiny'+method,observation_scope='Visible intake controls; no submission',
                      note=state['note'],url=url)
    store.row_update(audit_id,row_id,result=result)
    store.event(audit_id,'intake_inspection',row_id+' '+method+': '+('verified exact visible controls' if verified else 'inconclusive inspection'))
    return state
