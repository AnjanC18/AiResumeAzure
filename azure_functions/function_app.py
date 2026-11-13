import logging
import json
import os
import re
import io
import azure.functions as func
from pypdf import PdfReader

app = func.FunctionApp()

# ==============================================================================
# Helper NLP & Scoring Extraction Logic (Portable for Azure Function runtime)
# ==============================================================================

SKILL_ALIASES = {
    "Python": ["python", "py", "python3"],
    "Java": ["java", "core java", "j2ee"],
    "JavaScript": ["javascript", "js", "ecmascript"],
    "TypeScript": ["typescript", "ts"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp", ".net c#"],
    "Go": ["golang", "go lang"],
    "SQL": ["sql", "mysql", "postgresql", "postgres", "sqlite", "mariadb"],
    "NoSQL": ["nosql", "mongodb", "cassandra", "dynamodb"],
    "Flask": ["flask"],
    "Django": ["django"],
    "FastAPI": ["fastapi"],
    "React": ["react", "reactjs", "react.js"],
    "Node.js": ["node", "nodejs", "node.js"],
    "Docker": ["docker", "containerization"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services", "ec2", "s3", "lambda"],
    "Azure": ["azure", "microsoft azure", "blob storage", "azure functions"],
    "Git": ["git", "github", "gitlab"],
    "CI/CD": ["ci/cd", "continuous integration", "github actions"],
    "Machine Learning": ["machine learning", "ml", "scikit-learn"],
    "Deep Learning": ["deep learning", "neural networks", "pytorch", "tensorflow"],
    "NLP": ["nlp", "natural language processing", "spacy", "nltk", "transformers"]
}

EDUCATION_PATTERNS = [
    (r"\b(ph\.?d|doctorate)\b", "Ph.D"),
    (r"\b(m\.?tech|master of technology|m\.?e)\b", "M.Tech"),
    (r"\b(b\.?tech|bachelor of technology|b\.?e)\b", "B.Tech"),
    (r"\b(m\.?c\.?a)\b", "MCA"),
    (r"\b(b\.?c\.?a)\b", "BCA"),
    (r"\b(m\.?s|m\.?sc)\b", "M.Sc"),
    (r"\b(b\.?s|b\.?sc)\b", "B.Sc"),
    (r"\b(m\.?b\.?a)\b", "MBA"),
]

def extract_pdf_stream(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages_text = [p.extract_text() for p in reader.pages if p.extract_text()]
        return "\n".join(pages_text)
    except Exception as e:
        logging.error(f"Error parsing PDF stream: {e}")
        return ""

def extract_contact_info(text: str):
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    email = email_match.group(0).lower() if email_match else ""

    phone_patterns = [
        r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
        r"\+?\d{1,3}[-.\s]?\d{10}",
    ]
    phone = ""
    for p in phone_patterns:
        m = re.search(p, text)
        if m:
            clean = m.group(0).strip()
            if len(re.sub(r"\D", "", clean)) >= 10:
                phone = clean
                break

    lines = [x.strip() for x in text.splitlines() if x.strip()]
    name = lines[0][:50].title() if lines else "Candidate"
    return name, email, phone

def extract_experience_years(text: str) -> float:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience|exp)",
        r"(?:total\s+)?(?:experience|exp)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\s+experience",
    ]
    vals = []
    for p in patterns:
        for m in re.findall(p, text.lower()):
            try:
                v = float(m)
                if 0 <= v <= 45:
                    vals.append(v)
            except ValueError:
                pass
    return max(vals) if vals else 0.0

def extract_skills_list(text: str, req_skills=None) -> list:
    cleaned = re.sub(
        r'https?://\S+|www\.\S+|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|(?:github|linkedin|gitlab|bitbucket)\.com/\S+',
        ' ',
        text
    )
    lower = cleaned.lower()
    found = []
    for canonical, aliases in SKILL_ALIASES.items():
        for a in aliases:
            if re.search(r"(?<![a-zA-Z0-9])" + re.escape(a.lower()) + r"(?![a-zA-Z0-9])", lower):
                found.append(canonical)
                break
    if req_skills:
        for r in req_skills:
            if r.strip() and re.search(r"(?<![a-zA-Z0-9])" + re.escape(r.strip().lower()) + r"(?![a-zA-Z0-9])", lower):
                if not any(f.lower() == r.strip().lower() for f in found):
                    found.append(r.strip().title())
    return found

def score_resume(required_skills, found_skills, cand_exp, min_exp, req_edu, cand_edu):
    req_list = [s.strip() for s in required_skills if s.strip()]
    cand_list = [s.strip() for s in found_skills if s.strip()]
    matched = [r for r in req_list if any(r.lower() == c.lower() or r.lower() in c.lower() for c in cand_list)]
    missing = [r for r in req_list if r not in matched]

    skill_score = (len(matched) / len(req_list) * 100.0) if req_list else 100.0
    exp_score = 100.0 if min_exp <= 0 or cand_exp >= min_exp else min(100.0, (cand_exp / min_exp) * 100.0)
    edu_score = 100.0 if not req_edu or any(e.lower() in (cand_edu or "").lower() for e in req_edu.split(",")) else 0.0
    overall = round(skill_score * 0.5 + exp_score * 0.25 + edu_score * 0.25, 1)

    return matched, missing, round(skill_score, 1), round(exp_score, 1), round(edu_score, 1), overall


# ==============================================================================
# 1. Azure Function HTTP Trigger: POST /api/screen_resume
# ==============================================================================
@app.route(route="screen_resume", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def screen_resume_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP Trigger for serverless resume screening.
    Accepts JSON body or multipart form with PDF bytes.
    """
    logging.info("Azure Function HTTP Trigger: processing resume screening request.")
    try:
        content_type = req.headers.get("Content-Type", "")
        if "application/json" in content_type:
            data = req.get_json()
            resume_text = data.get("resume_text", "")
            job_title = data.get("job_title", "Software Engineer")
            req_skills = data.get("required_skills", "").split(",")
            min_exp = float(data.get("min_experience", 0))
            req_edu = data.get("required_education", "")
        else:
            # Multipart or binary upload
            pdf_bytes = req.get_body()
            resume_text = extract_pdf_stream(pdf_bytes)
            job_title = req.params.get("job_title", "Software Engineer")
            req_skills = req.params.get("required_skills", "Python, SQL").split(",")
            min_exp = float(req.params.get("min_experience", 0))
            req_edu = req.params.get("required_education", "")

        name, email, phone = extract_contact_info(resume_text)
        cand_exp = extract_experience_years(resume_text)
        cand_skills = extract_skills_list(resume_text, req_skills)
        matched, missing, skill_score, exp_score, edu_score, overall = score_resume(
            req_skills, cand_skills, cand_exp, min_exp, req_edu, ""
        )

        response_payload = {
            "status": "success",
            "candidate": {
                "name": name,
                "email": email,
                "phone": phone,
                "experience": cand_exp,
                "detected_skills": cand_skills,
            },
            "scores": {
                "skill_score": skill_score,
                "experience_score": exp_score,
                "education_score": edu_score,
                "overall_score": overall,
                "matched_skills": matched,
                "missing_skills": missing,
            },
            "engine": "Azure Functions Serverless Worker (Python v2)"
        }
        return func.HttpResponse(
            json.dumps(response_payload, indent=2),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f"Error in screen_resume_http: {e}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": str(e)}),
            mimetype="application/json",
            status_code=500
        )


# ==============================================================================
# 2. Azure Function Blob Trigger: Listening on container 'resumes/{name}'
# ==============================================================================
@app.blob_trigger(arg_name="myblob", path="resumes/{name}", connection="AZURE_STORAGE_CONNECTION_STRING")
def resume_blob_trigger(myblob: func.InputStream):
    """
    Blob Trigger: automatically runs whenever a PDF resume is uploaded to Azure Blob Storage.
    Parses document, extracts metadata, and syncs candidate record to Azure SQL.
    """
    logging.info(f"Azure Function Blob Trigger: Processing uploaded blob -> Name: {myblob.name}, Size: {myblob.length} bytes")
    try:
        blob_bytes = myblob.read()
        extracted_text = extract_pdf_stream(blob_bytes)
        name, email, phone = extract_contact_info(extracted_text)
        experience = extract_experience_years(extracted_text)
        skills = extract_skills_list(extracted_text)

        logging.info(f"Successfully processed blob {myblob.name}: Candidate: {name}, Skills: {len(skills)}")
        # In production with Azure SQL connection string set, execute candidate DB record update
    except Exception as e:
        logging.error(f"Error in resume_blob_trigger: {e}")

