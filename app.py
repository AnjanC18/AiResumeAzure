import os
import re
import sqlite3
import time
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_from_directory,
    jsonify,
    abort
)
from werkzeug.utils import secure_filename
from pypdf import PdfReader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "resume_screening.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me-12345")
ALLOWED_EXTENSIONS = {"pdf"}

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
    "Azure": ["azure", "microsoft azure", "azure devops", "blob storage", "azure functions"],
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

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        department TEXT DEFAULT 'Engineering',
        description TEXT,
        required_skills TEXT NOT NULL,
        min_experience REAL DEFAULT 0,
        education TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        name TEXT,
        email TEXT,
        phone TEXT,
        resume_filename TEXT NOT NULL,
        extracted_text TEXT,
        skills TEXT,
        education TEXT,
        experience REAL DEFAULT 0,
        skill_score REAL DEFAULT 0,
        experience_score REAL DEFAULT 0,
        education_score REAL DEFAULT 0,
        overall_score REAL DEFAULT 0,
        matched_skills TEXT,
        missing_skills TEXT,
        status TEXT DEFAULT 'Under Review',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    conn.close()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_pdf_text(path):
    try:
        reader = PdfReader(path)
        extracted = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                extracted.append(t)
        return "\n".join(extracted)
    except Exception as e:
        print(f"Error reading PDF {path}: {e}")
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
    lower = text.lower()
    found = []
    
    # 1. Check configured aliases
    for canonical, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            # Match whole words or boundary
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(alias.lower()) + r"(?![a-zA-Z0-9])"
            if re.search(pattern, lower):
                if canonical not in found:
                    found.append(canonical)
                break
                
    # 2. Dynamic check for any custom required skills
    if required_skills:
        for req in required_skills:
            if not req.strip():
                continue
            req_clean = req.strip()
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(req_clean.lower()) + r"(?![a-zA-Z0-9])"
            if re.search(pattern, lower):
                # Check if already added (case-insensitive)
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

def score_candidate(required_skills, candidate_skills, candidate_exp, min_exp, required_education, candidate_education):
    req_list = [s.strip() for s in required_skills if s.strip()]
    cand_list = [s.strip() for s in candidate_skills if s.strip()]
    
    matched = []
    missing = []
    
    for req in req_list:
        is_matched = False
        req_lower = req.lower()
        
        # 1. Direct match with candidate skills
        for cand in cand_list:
            cand_lower = cand.lower()
            if req_lower == cand_lower or req_lower in cand_lower or cand_lower in req_lower:
                is_matched = True
                break
                
        # 2. Alias match
        if not is_matched:
            for canonical, aliases in SKILL_ALIASES.items():
                if req_lower == canonical.lower() or req_lower in aliases:
                    # check if any alias is in cand_list
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
        
    overall = round(skill_score * 0.50 + exp_score * 0.25 + edu_score * 0.25, 1)
    return sorted(matched), sorted(missing), round(skill_score, 1), round(exp_score, 1), round(edu_score, 1), overall

@app.route("/")
def index():
    conn = get_db()
    jobs = conn.execute("""
        SELECT j.*, 
               COUNT(c.id) AS candidate_count,
               AVG(c.overall_score) AS avg_score,
               SUM(CASE WHEN c.status = 'Shortlisted' THEN 1 ELSE 0 END) AS shortlisted_count
        FROM jobs j
        LEFT JOIN candidates c ON j.id = c.job_id
        GROUP BY j.id
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
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO jobs(title, department, description, required_skills, min_experience, education) VALUES(?,?,?,?,?,?)",
            (title, department, description, skills, min_exp, education)
        )
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        flash(f"Job posting '{title}' created successfully!", "success")
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
    
    # Summary stats for this job
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
        save_path = os.path.join(UPLOAD_DIR, unique_name)
        
        try:
            file.save(save_path)
            extracted_text = extract_pdf_text(save_path)
            
            if not extracted_text.strip():
                # Text was empty, maybe image-based PDF or corrupted
                extracted_text = f"Candidate Resume ({original_name})"
                
            name = extract_name(extracted_text)
            email = extract_email(extracted_text)
            phone = extract_phone(extracted_text)
            experience = extract_experience(extracted_text)
            education = extract_education(extracted_text)
            skills = extract_skills(extracted_text, required_skills)
            
            matched, missing, skill_score, exp_score, edu_score, overall = score_candidate(
                required_skills, skills, experience, min_experience, required_education, education
            )
            
            conn.execute("""
                INSERT INTO candidates (
                    job_id, name, email, phone, resume_filename, extracted_text, 
                    skills, education, experience, skill_score, experience_score, 
                    education_score, overall_score, matched_skills, missing_skills, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, name, email, phone, unique_name, extracted_text,
                ", ".join(skills), education, experience,
                skill_score, exp_score, edu_score, overall,
                ", ".join(matched), ", ".join(missing), "Under Review"
            ))
            uploaded_count += 1
        except Exception as exc:
            errors.append(f"{original_name}: {exc}")

    conn.commit()
    conn.close()

    if uploaded_count > 0:
        flash(f"Successfully processed {uploaded_count} resume(s) with AI screening!", "success")
    if errors:
        for err in errors:
            flash(f"Error: {err}", "danger")

    return redirect(url_for("job_detail", job_id=job_id))

@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    conn = get_db()
    # Get candidate resume files to remove them
    candidates = conn.execute("SELECT resume_filename FROM candidates WHERE job_id = ?", (job_id,)).fetchall()
    for c in candidates:
        filepath = os.path.join(UPLOAD_DIR, c["resume_filename"])
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
    conn.execute("DELETE FROM candidates WHERE job_id = ?", (job_id,))
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    flash("Job and associated candidates deleted successfully.", "info")
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
        filepath = os.path.join(UPLOAD_DIR, candidate["resume_filename"])
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
        conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
        conn.commit()
        conn.close()
        flash("Candidate removed.", "info")
        return redirect(url_for("job_detail", job_id=job_id))
    conn.close()
    return redirect(url_for("index"))

@app.route("/uploads/<path:filename>")
def view_resume(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/seed-demo", methods=["POST"])
def seed_demo_data():
    conn = get_db()
    
    # 1. Job 1: Senior Full Stack Python Developer
    cur = conn.cursor()
    cur.execute("""
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
    job1_id = cur.lastrowid
    
    # 2. Job 2: AI / ML Engineer
    cur.execute("""
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
    job2_id = cur.lastrowid
    
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
            "exp_score": 100.0,
            "edu_score": 100.0,
            "overall_score": 100.0,
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
            "exp_score": 83.3,
            "edu_score": 100.0,
            "overall_score": 77.1,
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
            "exp_score": 33.3,
            "edu_score": 0.0,
            "overall_score": 20.8,
            "matched": "Git, React",
            "missing": "AWS, Docker, Flask, Python, REST API, SQL",
            "status": "Rejected",
            "text": "Emily Chen\nEmail: emily.chen@example.com\nPhone: +1 (555) 345-6789\n\nFrontend developer with 1 year experience building UI with React and JavaScript.\n\nEducation: BCA\nSkills: React, JavaScript, HTML/CSS, Git"
        }
    ]
    
    for c in sample_candidates_job1:
        conn.execute("""
            INSERT INTO candidates (
                job_id, name, email, phone, resume_filename, extracted_text,
                skills, education, experience, skill_score, experience_score,
                education_score, overall_score, matched_skills, missing_skills, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job1_id, c["name"], c["email"], c["phone"], c["filename"], c["text"],
            c["skills"], c["education"], c["experience"], c["skill_score"],
            c["exp_score"], c["edu_score"], c["overall_score"], c["matched"],
            c["missing"], c["status"]
        ))
        
    conn.commit()
    conn.close()
    flash("Sample demo jobs & candidates loaded successfully!", "success")
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] AI Resume Screening MVP is running at http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
