import os
import re
import time
import io
import html
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    jsonify,
    abort
)
from markupsafe import Markup
from werkzeug.utils import secure_filename
from pypdf import PdfReader

# Azure Cloud Architecture Modules
from config import Config
from db import get_db, init_db
from storage import storage_service
from ai_matcher import semantic_matcher

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
ALLOWED_EXTENSIONS = Config.ALLOWED_EXTENSIONS


@app.context_processor
def inject_cloud_context():
    """Injects live Azure Cloud Status into every Jinja2 template."""
    return {
        "cloud_status": Config.get_cloud_status()
    }


# ==============================================================================
# Skill Aliases & Heuristic Taxonomy
# ==============================================================================
SKILL_ALIASES = {
    "Python": ["python", "py", "python3"],
    "Java": ["java", "core java", "j2ee"],
    "JavaScript": ["javascript", "js", "ecmascript"],
    "TypeScript": ["typescript", "ts"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp", ".net c#", "c#.net"],
    "Go": ["golang", "go lang", "go language"],
    "Rust": ["rust", "rustlang"],
    "PHP": ["php", "laravel"],
    "Ruby": ["ruby", "ruby on rails", "rails"],
    "Swift": ["swift", "swiftui", "ios development"],
    "Kotlin": ["kotlin", "android development"],
    "SQL": ["sql", "mysql", "postgresql", "postgres", "pl/sql", "t-sql", "sqlite", "mariadb"],
    "NoSQL": ["nosql", "mongodb", "cassandra", "dynamodb", "couchbase", "firestore"],
    "Redis": ["redis"],
    "Flask": ["flask"],
    "Django": ["django"],
    "FastAPI": ["fastapi", "fast-api"],
    "Spring Boot": ["spring boot", "springboot", "spring framework", "spring"],
    "React": ["react", "reactjs", "react.js", "react native"],
    "Angular": ["angular", "angularjs", "angular 2+"],
    "Vue.js": ["vue", "vuejs", "vue.js", "nuxt", "nuxtjs"],
    "Next.js": ["next.js", "nextjs", "next"],
    "Node.js": ["node", "nodejs", "node.js"],
    "Express.js": ["express", "expressjs", "express.js"],
    "REST API": ["rest api", "restful api", "rest api development", "api development", "rest apis", "restful web services"],
    "GraphQL": ["graphql", "graph ql"],
    "HTML/CSS": ["html", "html5", "css", "css3", "sass", "scss", "tailwind", "bootstrap"],
    "Git": ["git", "github", "gitlab", "bitbucket", "version control"],
    "Docker": ["docker", "containerization", "dockerfile", "docker-compose"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services", "ec2", "s3", "lambda", "rds", "cloudformation", "iam"],
    "Azure": ["azure", "microsoft azure", "azure devops", "blob storage", "azure functions", "azure sql"],
    "GCP": ["gcp", "google cloud", "google cloud platform", "bigquery"],
    "CI/CD": ["ci/cd", "continuous integration", "continuous deployment", "jenkins", "github actions", "gitlab ci"],
    "Linux": ["linux", "ubuntu", "centos", "redhat", "bash", "shell scripting"],
    "Machine Learning": ["machine learning", "ml", "supervised learning", "unsupervised learning", "scikit-learn", "sklearn"],
    "Deep Learning": ["deep learning", "neural networks", "cnn", "rnn", "lstm", "transformers"],
    "PyTorch": ["pytorch", "torch"],
    "TensorFlow": ["tensorflow", "keras"],
    "NLP": ["nlp", "natural language processing", "spacy", "nltk", "hugging face", "bert", "llm", "large language models", "generative ai"],
    "Computer Vision": ["computer vision", "opencv", "cv", "image processing", "yolo"],
    "Data Analysis": ["data analysis", "data analytics", "pandas", "numpy", "matplotlib", "seaborn"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Agile": ["agile", "scrum", "kanban", "jira", "sprint planning"],
    "Cybersecurity": ["cybersecurity", "cyber security", "penetration testing", "owasp", "soc", "siem"],
    "Microservices": ["microservices", "microservice architecture", "distributed systems"],
}


URL_OR_EMAIL_REGEX = re.compile(
    r'(https?://[^\s<>"\']+|www\.[^\s<>"\']+|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|(?:github|linkedin|gitlab|bitbucket)\.com/[^\s<>"\']+)'
)


@app.template_filter("highlight_resume_skills")
def highlight_resume_skills(text, skills_str="", matched_skills_str=""):
    """
    Highlights detected skills and matched skills in the raw resume text.
    - URLs and email addresses are preserved as clean links and NOT highlighted as skills.
    - Matched job requirements are highlighted in green (.highlight-matched)
    - Other detected candidate skills are highlighted in indigo (.highlight-extracted)
    """
    if not text:
        return ""

    candidate_skills = [s.strip() for s in (skills_str or "").split(",") if s.strip()]
    matched_skills = [s.strip().lower() for s in (matched_skills_str or "").split(",") if s.strip()]

    terms_map = {}
    for skill in candidate_skills:
        skill_lower = skill.lower()
        is_matched = (skill_lower in matched_skills) or any(
            m == skill_lower or m in skill_lower or skill_lower in m for m in matched_skills
        )
        terms_map[skill_lower] = is_matched

        # Add all aliases for canonical skill
        for canonical, aliases in SKILL_ALIASES.items():
            if canonical.lower() == skill_lower or skill_lower in [a.lower() for a in aliases]:
                for alias in aliases:
                    if alias.lower() not in terms_map:
                        terms_map[alias.lower()] = is_matched
                terms_map[canonical.lower()] = is_matched

    # Split text into alternating (normal_text, url_or_email) parts
    parts = URL_OR_EMAIL_REGEX.split(text)

    sorted_terms = sorted(terms_map.keys(), key=lambda t: len(t), reverse=True) if terms_map else []
    if sorted_terms:
        skill_pattern = re.compile(
            r"(?i)(?<![a-zA-Z0-9_@])("
            + "|".join(re.escape(t) for t in sorted_terms)
            + r")(?![a-zA-Z0-9_@])"
        )
    else:
        skill_pattern = None

    def replacer(match):
        token = match.group(1)
        token_lower = token.lower()
        is_matched = terms_map.get(token_lower, False)

        # Fallback check against matched skills
        if not is_matched:
            for canonical, aliases in SKILL_ALIASES.items():
                if token_lower == canonical.lower() or token_lower in [a.lower() for a in aliases]:
                    if canonical.lower() in matched_skills or any(m in [a.lower() for a in aliases] for m in matched_skills):
                        is_matched = True
                        break

        if is_matched:
            return f'<mark class="highlight-matched" title="Matched Job Requirement: {html.escape(token)}">{token}</mark>'
        else:
            return f'<mark class="highlight-extracted" title="Detected Skill: {html.escape(token)}">{token}</mark>'

    result = []
    for i, part in enumerate(parts):
        if not part:
            continue
        # Odd index represents a matched URL or email address
        if i % 2 == 1:
            escaped_part = html.escape(part)
            if "@" in part and not part.startswith("http"):
                href = f"mailto:{escaped_part}"
            elif part.startswith("http://") or part.startswith("https://"):
                href = escaped_part
            else:
                href = f"https://{escaped_part}"
            result.append(f'<a href="{href}" target="_blank" class="text-primary text-decoration-underline" style="word-break: break-all;">{escaped_part}</a>')
        else:
            escaped_text = html.escape(part)
            if skill_pattern:
                escaped_text = skill_pattern.sub(replacer, escaped_text)
            result.append(escaped_text)

    return Markup("".join(result))


EDUCATION_PATTERNS = [
    (r"\b(ph\.?d|doctorate|doctor of philosophy)\b", "Ph.D"),
    (r"\b(m\.?tech|master of technology|m\.?e|master of engineering)\b", "M.Tech"),
    (r"\b(b\.?tech|bachelor of technology|b\.?e|bachelor of engineering)\b", "B.Tech"),
    (r"\b(m\.?c\.?a|master of computer applications?)\b", "MCA"),
    (r"\b(b\.?c\.?a|bachelor of computer applications?)\b", "BCA"),
    (r"\b(m\.?s|m\.?sc|master of science)\b", "M.Sc"),
    (r"\b(b\.?s|b\.?sc|bachelor of science)\b", "B.Sc"),
    (r"\b(m\.?b\.?a|master of business administration)\b", "MBA"),
    (r"\b(b\.?b\.?a|bachelor of business administration)\b", "BBA"),
    (r"\b(b\.?com|bachelor of commerce)\b", "B.Com"),
    (r"\b(m\.?com|master of commerce)\b", "M.Com"),
    (r"\b(diploma)\b", "Diploma"),
]


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_pdf_text(path_or_stream):
    try:
        reader = PdfReader(path_or_stream)
        extracted = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted.append(t)
        return "\n".join(extracted)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""


def extract_email(text):
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0).lower() if match else ""


def extract_phone(text):
    patterns = [
        r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
        r"\+?\d{1,3}[-.\s]?\d{10}",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            clean = m.group(0).strip()
            digits = re.sub(r"\D", "", clean)
            if len(digits) >= 10:
                return clean
    return ""


def extract_name(text):
    ignore_words = {
        "curriculum", "vitae", "resume", "biodata", "profile", "contact", 
        "email", "phone", "summary", "page", "education", "experience", 
        "skills", "projects", "work", "career", "objective", "address"
    }
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for line in lines[:15]:
        words = line.split()
        if 2 <= len(words) <= 4:
            lower_line = line.lower()
            if not any(w in lower_line for w in ignore_words) and "@" not in line and not any(ch.isdigit() for ch in line):
                clean = re.sub(r"[^\w\s]", "", line).strip()
                if clean and len(clean) >= 3:
                    return clean.title()
    if lines:
        first_clean = re.sub(r"[^\w\s]", "", lines[0]).strip()
        if first_clean:
            return first_clean[:50].title()
    return "Candidate"


def extract_experience(text):
    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience|exp|relevant\s+experience)",
        r"(?:total\s+)?(?:experience|exp)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:in|working\s+as|as\s+a|with|developing)",
        r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\s+experience",
    ]
    values = []
    lower = text.lower()
    for p in patterns:
        for match in re.findall(p, lower):
            try:
                val = float(match)
                if 0 <= val <= 50:
                    values.append(val)
            except ValueError:
                pass
    return max(values) if values else 0.0


def extract_education(text):
    lower = text.lower()
    found = []
    for pattern, label in EDUCATION_PATTERNS:
        if re.search(pattern, lower):
            if label not in found:
                found.append(label)
    return ", ".join(found)


def extract_skills(text, required_skills=None):
    # Strip URLs, web domains, and email addresses so profile links (e.g. https://github.com/username)
    # do not falsely trigger skill detection.
    cleaned_text = re.sub(
        r'https?://\S+|www\.\S+|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|(?:github|linkedin|gitlab|bitbucket)\.com/\S+',
        ' ',
        text
    )
    lower = cleaned_text.lower()
    found = []
    
    # 1. Check configured aliases
    for canonical, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(alias.lower()) + r"(?![a-zA-Z0-9])"
            if re.search(pattern, lower):
                if canonical not in found:
                    found.append(canonical)
                break
                
    # 2. Dynamic check for custom required skills
    if required_skills:
        for req in required_skills:
            if not req.strip():
                continue
            req_clean = req.strip()
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(req_clean.lower()) + r"(?![a-zA-Z0-9])"
            if re.search(pattern, lower):
                if not any(f.lower() == req_clean.lower() for f in found):
                    found.append(req_clean.title())
                    
    return found


def parse_required_skills(raw):
    parts = re.split(r"[,\n;]+", raw or "")
    clean = []
    for x in parts:
        s = x.strip()
        if s and s.lower() not in [c.lower() for c in clean]:
            clean.append(s)
    return clean


def score_candidate(required_skills, candidate_skills, candidate_exp, min_exp, required_education, candidate_education, semantic_score=0.0):
    req_list = [s.strip() for s in required_skills if s.strip()]
    cand_list = [s.strip() for s in candidate_skills if s.strip()]
    
    matched = []
    missing = []
    
    for req in req_list:
        is_matched = False
        req_lower = req.lower()
        
        # 1. Direct match
        for cand in cand_list:
            cand_lower = cand.lower()
            if req_lower == cand_lower or req_lower in cand_lower or cand_lower in req_lower:
                is_matched = True
                break
                
        # 2. Alias match
        if not is_matched:
            for canonical, aliases in SKILL_ALIASES.items():
                if req_lower == canonical.lower() or req_lower in aliases:
                    if any(c.lower() == canonical.lower() or c.lower() in aliases for c in cand_list):
                        is_matched = True
                        break
                        
        if is_matched:
            matched.append(req)
        else:
            missing.append(req)
            
    skill_score = (len(matched) / len(req_list) * 100.0) if req_list else 100.0
    
    # Experience score
    if min_exp <= 0:
        exp_score = 100.0
    elif candidate_exp >= min_exp:
        exp_score = 100.0
    else:
        exp_score = min(100.0, (candidate_exp / min_exp) * 100.0)
        
    # Education score
    req_edu_str = (required_education or "").strip()
    if not req_edu_str:
        edu_score = 100.0
    else:
        req_edus = [x.strip().lower() for x in re.split(r"[,\n;/|]+", req_edu_str) if x.strip()]
        cand_edus = [x.strip().lower() for x in re.split(r"[,\n;/|]+", candidate_education or "") if x.strip()]
        
        has_match = False
        for r_edu in req_edus:
            for c_edu in cand_edus:
                if r_edu == c_edu or r_edu in c_edu or c_edu in r_edu:
                    has_match = True
                    break
            if has_match:
                break
        edu_score = 100.0 if has_match else 0.0
        
    # Explainable Composite Score: 
    # Skill (40%) + Semantic AI (20%) + Experience (20%) + Education (20%)
    overall = round(skill_score * 0.40 + semantic_score * 0.20 + exp_score * 0.20 + edu_score * 0.20, 1)
    return sorted(matched), sorted(missing), round(skill_score, 1), round(exp_score, 1), round(edu_score, 1), round(semantic_score, 1), overall


# ==============================================================================
# Web Routes
# ==============================================================================

@app.route("/")
def index():
    conn = get_db()
    jobs = conn.execute("""
        SELECT j.id, j.title, j.department, j.description, j.required_skills, j.min_experience, j.education, j.created_at,
               COUNT(c.id) AS candidate_count,
               AVG(c.overall_score) AS avg_score,
               SUM(CASE WHEN c.status = 'Shortlisted' THEN 1 ELSE 0 END) AS shortlisted_count
        FROM jobs j
        LEFT JOIN candidates c ON j.id = c.job_id
        GROUP BY j.id, j.title, j.department, j.description, j.required_skills, j.min_experience, j.education, j.created_at
        ORDER BY j.id DESC
    """).fetchall()
    
    stats = conn.execute("""
        SELECT 
            (SELECT COUNT(*) FROM jobs) AS total_jobs,
            (SELECT COUNT(*) FROM candidates) AS total_candidates,
            (SELECT COUNT(*) FROM candidates WHERE status = 'Shortlisted') AS total_shortlisted,
            (SELECT AVG(overall_score) FROM candidates) AS overall_avg_score
    """).fetchone()
    
    conn.close()
    return render_template("index.html", jobs=jobs, stats=stats)


@app.route("/jobs/new", methods=["GET", "POST"])
def new_job():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        department = request.form.get("department", "Engineering").strip()
        description = request.form.get("description", "").strip()
        skills = request.form.get("required_skills", "").strip()
        min_exp = float(request.form.get("min_experience") or 0)
        education = request.form.get("education", "").strip()
        
        if not title or not skills:
            flash("Job title and required skills are required.", "danger")
            return redirect(url_for("new_job"))
            
        conn = get_db()
        job_id = conn.execute_insert(
            "INSERT INTO jobs(title, department, description, required_skills, min_experience, education) VALUES(?,?,?,?,?,?)",
            (title, department, description, skills, min_exp, education)
        )
        conn.close()
        flash(f"Job opening '{title}' created successfully!", "success")
        return redirect(url_for("job_detail", job_id=job_id))
    return render_template("new_job.html")


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    status_filter = request.args.get("status", "all")
    sort_by = request.args.get("sort", "score_desc")
    search_q = request.args.get("q", "").strip()

    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        conn.close()
        flash("Job not found.", "danger")
        return redirect(url_for("index"))
        
    query = "SELECT * FROM candidates WHERE job_id = ?"
    params = [job_id]
    
    if status_filter != "all":
        query += " AND status = ?"
        params.append(status_filter)
        
    if search_q:
        query += " AND (name LIKE ? OR email LIKE ? OR skills LIKE ?)"
        term = f"%{search_q}%"
        params.extend([term, term, term])
        
    if sort_by == "score_asc":
        query += " ORDER BY overall_score ASC"
    elif sort_by == "date_desc":
        query += " ORDER BY id DESC"
    elif sort_by == "experience_desc":
        query += " ORDER BY experience DESC"
    else:
        query += " ORDER BY overall_score DESC"
        
    candidates = conn.execute(query, params).fetchall()
    
    job_stats = conn.execute("""
        SELECT 
            COUNT(*) AS total,
            AVG(overall_score) AS avg_score,
            SUM(CASE WHEN status = 'Shortlisted' THEN 1 ELSE 0 END) AS shortlisted,
            SUM(CASE WHEN status = 'Under Review' THEN 1 ELSE 0 END) AS under_review,
            SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) AS rejected
        FROM candidates WHERE job_id = ?
    """, (job_id,)).fetchone()
    
    conn.close()
    return render_template(
        "job_detail.html", 
        job=job, 
        candidates=candidates, 
        stats=job_stats, 
        status_filter=status_filter, 
        sort_by=sort_by,
        search_q=search_q
    )


@app.route("/jobs/<int:job_id>/upload", methods=["POST"])
def upload_resume(job_id):
    conn = get_db()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        conn.close()
        flash("Job not found.", "danger")
        return redirect(url_for("index"))

    files = request.files.getlist("resume")
    if not files or all(f.filename == "" for f in files):
        conn.close()
        flash("Please select at least one PDF resume.", "warning")
        return redirect(url_for("job_detail", job_id=job_id))

    required_skills = parse_required_skills(job["required_skills"])
    min_experience = float(job["min_experience"] or 0)
    required_education = job["education"] or ""
    job_desc_context = f"{job['title']} {job['description'] or ''} Required Skills: {job['required_skills']}"

    uploaded_count = 0
    errors = []

    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename):
            errors.append(f"{file.filename}: only PDF files are supported.")
            continue
            
        original_name = secure_filename(file.filename)
        unique_name = f"{job_id}_{int(time.time())}_{original_name}"
        
        try:
            # Stage 2: Save to Azure Blob Storage (or local storage fallback)
            saved_name, blob_url, storage_type = storage_service.save_resume(file, unique_name)
            
            # Extract PDF Text
            local_path = os.path.join(Config.UPLOAD_DIR, unique_name)
            extracted_text = extract_pdf_text(local_path)
            
            if not extracted_text.strip():
                extracted_text = f"Candidate Resume ({original_name})"
                
            name = extract_name(extracted_text)
            email = extract_email(extracted_text)
            phone = extract_phone(extracted_text)
            experience = extract_experience(extracted_text)
            education = extract_education(extracted_text)
            skills = extract_skills(extracted_text, required_skills)
            
            # Stage 4: Azure AI / Semantic Similarity Matching
            semantic_score, engine_name, sem_explanation = semantic_matcher.compute_similarity(
                job_desc_context, extracted_text
            )
            
            matched, missing, skill_score, exp_score, edu_score, sem_score, overall = score_candidate(
                required_skills, skills, experience, min_experience, required_education, education, semantic_score
            )
            
            # Stage 1: Write to Azure SQL Database (or local SQLite)
            conn.execute_insert("""
                INSERT INTO candidates (
                    job_id, name, email, phone, resume_filename, resume_blob_url, extracted_text, 
                    skills, education, experience, skill_score, experience_score, 
                    education_score, semantic_score, overall_score, matched_skills, missing_skills, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, name, email, phone, unique_name, blob_url or "", extracted_text,
                ", ".join(skills), education, experience,
                skill_score, exp_score, edu_score, sem_score, overall,
                ", ".join(matched), ", ".join(missing), "Under Review"
            ))
            uploaded_count += 1
        except Exception as exc:
            errors.append(f"{original_name}: {exc}")

    conn.close()

    if uploaded_count > 0:
        flash(f"Processed {uploaded_count} resume(s) with Azure Cloud AI Screening!", "success")
    if errors:
        for err in errors:
            flash(f"Error: {err}", "danger")

    return redirect(url_for("job_detail", job_id=job_id))


@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    conn = get_db()
    candidates = conn.execute("SELECT resume_filename FROM candidates WHERE job_id = ?", (job_id,)).fetchall()
    for c in candidates:
        storage_service.delete_resume(c["resume_filename"])
        
    conn.execute("DELETE FROM candidates WHERE job_id = ?", (job_id,))
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    flash("Job requisition and candidate records deleted successfully.", "info")
    return redirect(url_for("index"))


@app.route("/candidates/<int:candidate_id>")
def candidate_detail(candidate_id):
    conn = get_db()
    candidate = conn.execute("""
        SELECT c.*, j.title AS job_title, j.department AS job_department,
               j.required_skills, j.min_experience AS job_min_experience,
               j.education AS required_education, j.description AS job_description
        FROM candidates c
        JOIN jobs j ON c.job_id = j.id
        WHERE c.id = ?
    """, (candidate_id,)).fetchone()
    conn.close()
    
    if not candidate:
        flash("Candidate not found.", "danger")
        return redirect(url_for("index"))
        
    return render_template("candidate_detail.html", candidate=candidate)


@app.route("/candidates/<int:candidate_id>/status", methods=["POST"])
def candidate_status(candidate_id):
    status = request.form.get("status", "Under Review")
    conn = get_db()
    candidate = conn.execute("SELECT job_id FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    if not candidate:
        conn.close()
        flash("Candidate not found.", "danger")
        return redirect(url_for("index"))
        
    conn.execute("UPDATE candidates SET status = ? WHERE id = ?", (status, candidate_id))
    conn.commit()
    conn.close()
    flash(f"Candidate status updated to '{status}'.", "success")
    return redirect(url_for("candidate_detail", candidate_id=candidate_id))


@app.route("/candidates/<int:candidate_id>/delete", methods=["POST"])
def delete_candidate(candidate_id):
    conn = get_db()
    candidate = conn.execute("SELECT job_id, resume_filename FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    if candidate:
        job_id = candidate["job_id"]
        storage_service.delete_resume(candidate["resume_filename"])
        conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
        conn.commit()
        conn.close()
        flash("Candidate removed.", "info")
        return redirect(url_for("job_detail", job_id=job_id))
    conn.close()
    return redirect(url_for("index"))


@app.route("/uploads/<path:filename>")
def view_resume(filename):
    """Serves resume from Azure Blob Storage or local storage fallback."""
    raw_bytes = storage_service.get_resume_bytes(filename)
    if raw_bytes:
        return send_file(
            io.BytesIO(raw_bytes),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=filename
        )
    abort(404)


@app.route("/api/cloud-status")
def api_cloud_status():
    """Returns the live deployment status of all 5 Azure architecture stages."""
    return jsonify({
        "status": "operational",
        "stages": Config.get_cloud_status()
    })


@app.route("/seed-demo", methods=["POST"])
def seed_demo_data():
    conn = get_db()
    
    # 1. Job 1: Senior Full Stack Python Developer
    job1_id = conn.execute_insert("""
        INSERT INTO jobs (title, department, description, required_skills, min_experience, education)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "Senior Full Stack Python Developer",
        "Engineering",
        "We are looking for an experienced Full Stack Engineer to lead web application development, microservices architecture, and cloud deployment.",
        "Python, Flask, React, SQL, Docker, REST API, Git, AWS",
        3.0,
        "B.Tech, MCA, B.E"
    ))
    
    # 2. Job 2: AI / ML Engineer
    job2_id = conn.execute_insert("""
        INSERT INTO jobs (title, department, description, required_skills, min_experience, education)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        "AI / ML Engineer",
        "Data & AI",
        "Join our AI lab to build generative AI solutions, NLP pipelines, and machine learning models for enterprise applications.",
        "Python, Machine Learning, Deep Learning, PyTorch, NLP, SQL, Pandas",
        2.0,
        "M.Tech, B.Tech, M.Sc, Ph.D"
    ))
    
    # Sample candidates for Job 1
    sample_candidates_job1 = [
        {
            "name": "Sarah Jenkins",
            "email": "sarah.jenkins@example.com",
            "phone": "+1 (555) 234-5678",
            "filename": f"{job1_id}_sample_sarah.pdf",
            "skills": "Python, Flask, React, SQL, Docker, REST API, Git, AWS, TypeScript",
            "education": "B.Tech",
            "experience": 4.5,
            "skill_score": 100.0,
            "semantic_score": 96.5,
            "exp_score": 100.0,
            "edu_score": 100.0,
            "overall_score": 99.3,
            "matched": "AWS, Docker, Flask, Git, Python, React, REST API, SQL",
            "missing": "",
            "status": "Shortlisted",
            "text": "Sarah Jenkins\nEmail: sarah.jenkins@example.com\nPhone: +1 (555) 234-5678\n\nProfile: Full stack engineer with 4.5 years of experience in Python, Flask, React, TypeScript, SQL, Docker, and AWS cloud architecture.\n\nEducation:\nB.Tech in Computer Science\n\nSkills:\nPython, Flask, React, SQL, PostgreSQL, Docker, AWS, Git, REST API, CI/CD"
        },
        {
            "name": "Alex Rodriguez",
            "email": "alex.rodriguez@example.com",
            "phone": "+1 (555) 876-5432",
            "filename": f"{job1_id}_sample_alex.pdf",
            "skills": "Python, Flask, SQL, Git, REST API",
            "education": "MCA",
            "experience": 2.5,
            "skill_score": 62.5,
            "semantic_score": 78.4,
            "exp_score": 83.3,
            "edu_score": 100.0,
            "overall_score": 77.3,
            "matched": "Flask, Git, Python, REST API, SQL",
            "missing": "AWS, Docker, React",
            "status": "Under Review",
            "text": "Alex Rodriguez\nEmail: alex.rodriguez@example.com\nPhone: +1 (555) 876-5432\n\nSummary: Backend Python developer with 2.5 years experience in REST API development, Flask, and SQL databases.\n\nEducation: MCA\n\nSkills: Python, Flask, SQL, MySQL, Git, REST API"
        },
        {
            "name": "Emily Chen",
            "email": "emily.chen@example.com",
            "phone": "+1 (555) 345-6789",
            "filename": f"{job1_id}_sample_emily.pdf",
            "skills": "JavaScript, React, HTML/CSS, Git",
            "education": "BCA",
            "experience": 1.0,
            "skill_score": 25.0,
            "semantic_score": 38.0,
            "exp_score": 33.3,
            "edu_score": 0.0,
            "overall_score": 24.3,
            "matched": "Git, React",
            "missing": "AWS, Docker, Flask, Python, REST API, SQL",
            "status": "Rejected",
            "text": "Emily Chen\nEmail: emily.chen@example.com\nPhone: +1 (555) 345-6789\n\nFrontend developer with 1 year experience building UI with React and JavaScript.\n\nEducation: BCA\nSkills: React, JavaScript, HTML/CSS, Git"
        }
    ]
    
    for c in sample_candidates_job1:
        conn.execute_insert("""
            INSERT INTO candidates (
                job_id, name, email, phone, resume_filename, resume_blob_url, extracted_text,
                skills, education, experience, skill_score, experience_score,
                education_score, semantic_score, overall_score, matched_skills, missing_skills, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job1_id, c["name"], c["email"], c["phone"], c["filename"], "", c["text"],
            c["skills"], c["education"], c["experience"], c["skill_score"],
            c["exp_score"], c["edu_score"], c["semantic_score"], c["overall_score"], c["matched"],
            c["missing"], c["status"]
        ))
        
    conn.close()
    flash("Sample demo jobs & candidates loaded successfully!", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    port = Config.PORT
    print(f"[*] AI Resume Screening Platform is running at http://127.0.0.1:{port}")
    print(f"[*] Cloud Architecture Status:")
    for k, v in Config.get_cloud_status().items():
        print(f"    - {k}: {v['label']}")
    app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)
