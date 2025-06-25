from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os
import shutil
import uuid
import ansible_runner
from typing import List
from pathlib import Path
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/deploy")
async def deploy_vm(
    request: Request,
    esxi_host: str = Form(...),
    esxi_user: str = Form(...),
    esxi_pass: str = Form(...),
    vm_name: str = Form(...),
    files: List[UploadFile] = File(...)
):
    # Create a unique folder for this deployment
    folder_id = str(uuid.uuid4())
    upload_dir = f"/tmp/{folder_id}"
    os.makedirs(upload_dir, exist_ok=True)

    ovf_path = None

    # Save all uploaded files with directory structure (safe)
    for file in files:
        safe_path = Path(file.filename).as_posix()  # Normalize path
        file_path = os.path.join(upload_dir, safe_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        if file.filename.endswith(".ovf"):
            ovf_path = file_path

    if not ovf_path:
        return templates.TemplateResponse("form.html", {
            "request": request,
            "result": "No .ovf file found in uploaded files.",
            "rc": 1
        })

    # Run Ansible playbook
    r = ansible_runner.run(
        private_data_dir=".",
        playbook="deploy_vm.yml",
        extravars={
            "esxi_host": esxi_host,
            "esxi_user": esxi_user,
            "esxi_pass": esxi_pass,
            "vm_name": vm_name,
            "ovf_path": ovf_path
        }
    )

    # Load logs and save to timestamped file
    result_path = r.config.artifact_dir
    log_file = os.path.join(result_path, "stdout")
    with open(log_file) as f:
        logs = f.read()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_save_dir = "logs"
    os.makedirs(log_save_dir, exist_ok=True)
    saved_log_file = os.path.join(log_save_dir, f"deploy_{timestamp}.log")
    with open(saved_log_file, "w") as f:
        f.write(logs)

    # Clean up uploaded files
    shutil.rmtree(upload_dir, ignore_errors=True)

    # Render with JS alert and redirect
    message = f"Deployment {'succeeded' if r.rc == 0 else 'failed'} with status: {r.status}"
    html = f"""
    <html><body>
    <script>
        alert('{message}');
        window.location.href = "/";
    </script>
    </body></html>
    """
    return HTMLResponse(content=html)
