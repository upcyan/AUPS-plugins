from fastapi import APIRouter, Depends
from ...web.websec import require_auth
from . import api
router=APIRouter()
@router.get('/haproxy/status')
def status(auth=Depends(require_auth)): return api.status()
@router.post('/haproxy/install')
def install(auth=Depends(require_auth)): return api.install()
@router.post('/haproxy/validate')
def validate(auth=Depends(require_auth)): return api.validate()
@router.post('/haproxy/reload')
def reload(auth=Depends(require_auth)): return api.reload()
@router.get('/haproxy/logs')
def logs(kind:str='access',limit:int=200,auth=Depends(require_auth)): return api.logs(kind,limit)
