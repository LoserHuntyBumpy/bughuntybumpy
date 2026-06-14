#!/usr/bin/env python3
# BugHuntyBumpy - Crowdsourced Bug-Bounty-Reporting-Gateway mit deterministischer Verifikation
# Copyright (C) 2026  Nope-im-not-pro  <nope-im-not-pro@keemail.me>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""BHB Layer-1 pie-web - rendert bughunty.yml in adaptives Formular.

View-Layer. Liest die vom pie-scanner erzeugte Spec, baut daraus ein
projektspezifisches HTML-Formular (Verhaltenskodex-Gate, Reframe-Editor,
Repro-Step-Editor, Proof-of-Context). Submit geht an casg-api (Layer 2).
Keine Geschaeftslogik hier - nur Render + Proxy-Weiterleitung.
"""
import os

import httpx
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

SPEC_PATH = os.getenv("SPEC_PATH", "/spec/bughunty.yml")
CASG_API = os.getenv("CASG_API", "http://casg-api:8000")

app = FastAPI(title="BHB pie-web")
templates = Jinja2Templates(directory="templates")


def load_spec():
    try:
        with open(SPEC_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None


@app.get("/health")
def health():
    return {"ok": True, "spec_present": load_spec() is not None}


@app.get("/", response_class=HTMLResponse)
def form(request: Request):
    spec = load_spec()
    if not spec:
        return HTMLResponse(
            "<h1>BHB</h1><p>Keine bughunty.yml. Erst pie-scanner laufen "
            "lassen: <code>docker compose run --rm pie-scanner &lt;org/repo&gt;"
            "</code></p>", status_code=503)
    return templates.TemplateResponse(
        "form.html", {"request": request, "spec": spec})


@app.post("/submit")
async def submit(request: Request):
    payload = await request.json()
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post("%s/api/submit" % CASG_API, json=payload)
            return JSONResponse(r.json(), status_code=r.status_code)
        except httpx.HTTPError as e:
            return JSONResponse({"error": "casg-api unreachable: %s" % e},
                                status_code=502)
