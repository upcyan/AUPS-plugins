from fastapi import APIRouter, Depends
from ...web.websec import require_auth
from . import api
router=APIRouter()
@router.get('/certmanager/certificates')
def certificates(auth=Depends(require_auth)): return {"providers":api.providers(),"certificates":api.list_certs()}
@router.post('/certmanager/issue')
def issue(body:dict=None,auth=Depends(require_auth)):
 b=body or {}; return api.request_cert(b.get('domain',''),b.get('email'),b.get('provider'))
@router.post('/certmanager/renew')
def renew(body:dict=None,auth=Depends(require_auth)): return api.renew((body or {}).get('provider'))
@router.post('/certmanager/delete')
def delete(body:dict=None,auth=Depends(require_auth)):
 b=body or {}; return api.delete_cert(b.get('provider',''),b.get('domain',''))
@router.post('/certmanager/update')
def update(body:dict=None,auth=Depends(require_auth)):
 b=body or {}; return api.request_cert(b.get('domain',''),b.get('email'),b.get('provider'))
