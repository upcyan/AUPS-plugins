from fastapi import APIRouter, Depends
from ...web.websec import require_auth
from . import service

router = APIRouter()

@router.get("/domainproxy/status")
def status(auth=Depends(require_auth)):
    return service.status()

@router.post("/domainproxy/config")
def configure(body: dict = None, auth=Depends(require_auth)):
    return service.configure(**(body or {}))

@router.post("/domainproxy/start")
def start(auth=Depends(require_auth)):
    return service.start()

@router.post("/domainproxy/stop")
def stop(auth=Depends(require_auth)):
    return service.stop()
