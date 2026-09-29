# AI Resume Screening MVP

## Run on Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

Create a job, then upload a PDF resume. The MVP extracts text, detects configured skills, education and experience, and calculates an explainable score.

## Next Azure stages

1. Replace SQLite with Azure SQL.
2. Upload resumes to Azure Blob Storage.
3. Move processing to Azure Functions.
4. Add Azure AI/semantic matching.
5. Deploy Flask to Azure App Service.

Do not commit secrets to Git.
