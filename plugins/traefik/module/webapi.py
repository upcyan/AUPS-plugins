from fastapi import APIRouter, Depends
from ...web.websec import require_auth
from . import api
router=APIRouter()
@router.get('/traefik/status')
def status(auth=Depends(require_auth)): return api.status()
@router.post('/traefik/install')
def install(auth=Depends(require_auth)): return api.install()
@router.post('/traefik/validate')
def validate(auth=Depends(require_auth)): return api.validate()
@router.post('/traefik/reload')
def reload(auth=Depends(require_auth)): return api.reload()
@router.get('/traefik/logs')
def logs(kind:str='access',limit:int=200,auth=Depends(require_auth)): return api.logs(kind,limit)
@router.post('/traefik/deploy')
def deploy(body:dict=None,auth=Depends(require_auth)): return api.set_deploy_method((body or {}).get('method',''))
