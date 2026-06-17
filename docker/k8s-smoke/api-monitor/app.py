from fastapi import FastAPI

app = FastAPI(title="Bifrost Monitor API (K3s stg smoke)")


@app.get("/status")
def status():
    return {"status": "ok", "service": "bifrost-api-monitor", "environment": "stg-smoke"}
