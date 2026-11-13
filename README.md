# AI-Powered Resume Screening & Candidate Ranking Platform

An explainable, cloud-native NLP screening and candidate evaluation platform built for high-volume automated talent acquisition.

```
                  RESUME PDF
                       │
                       ↓
                Azure Blob Storage
                       │
                       ↓
                 Azure Function
                       │
                       ↓
              Document Processing
                       │
                       ↓
              Resume Information
                       │
          ┌────────────┼────────────┐
          ↓            ↓            ↓
       Skills      Education    Experience
          │            │            │
          └────────────┼────────────┘
                       ↓
                 AI Matching
                       ↑
                       │
                 Job Description
                       │
                       ↓
                Scoring Engine
                       │
          ┌────────────┼────────────┐
          ↓            ↓            ↓
      Match Score   Skill Gap   Explanation
          │            │            │
          └────────────┼────────────┘
                       ↓
               Recruiter Dashboard
```

---

## 🌟 Key Features & Azure Architecture

The platform implements the complete 5-stage Azure Cloud Architecture:

| # | Architecture Stage | Implementation Details | Cloud Component | Local Fallback |
|---|---|---|---|---|
| **1** | **Database Storage** | Replaced SQLite with unified DB layer supporting Azure SQL Database | `Azure SQL / ODBC Driver 18` | SQLite (`resume_screening.db`) |
| **2** | **Resume Storage** | Uploads candidate resumes to secure blob containers | `Azure Blob Storage` (`resumes`) | Local Filesystem (`uploads/`) |
| **3** | **Serverless Workers** | Serverless PDF ingestion & asynchronous parsing pipeline | `Azure Functions (Python v2)` | In-App Extraction Pipeline |
| **4** | **Semantic AI Matching** | Contextual relevance scoring with neural embeddings | `Azure OpenAI Embeddings` | Domain TF-IDF Vectorizer |
| **5** | **Cloud Deployment** | Production containerization & automated cloud hosting | `Azure App Service (Linux Web App)` | Localhost (`5000`) |

---

## 🚀 Quickstart: Run Locally

### 1. Prerequisites & Virtual Environment
```powershell
# Create and activate virtual environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install production dependencies
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
*(If no Azure credentials are provided in `.env`, the system runs in offline/local fallback mode automatically).*

### 3. Start the Application
```powershell
python app.py
```
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser.

---

## ☁️ Azure Cloud Deployment (Stage by Stage)

### Stage 1: Azure SQL Database Setup
1. Provision Azure SQL Server & Database in the Azure Portal or via Azure CLI:
   ```powershell
   az sql server create --name sql-airesume --resource-group rg-ai-resume --location eastus --admin-user cloudadmin --admin-password "YourStrongPassword!"
   az sql db create --resource-group rg-ai-resume --server sql-airesume --name resume_screening_db --service-objective Basic
   ```
2. Set the connection string in your `.env` or App Service configuration:
   ```env
   AZURE_SQL_CONNECTION_STRING="Driver={ODBC Driver 18 for SQL Server};Server=tcp:sql-airesume.database.windows.net,1433;Database=resume_screening_db;Uid=cloudadmin;Pwd=YourStrongPassword!;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
   ```

### Stage 2: Azure Blob Storage Setup
1. Create storage account and blob container:
   ```powershell
   az storage account create --name saairesumes --resource-group rg-ai-resume --location eastus --sku Standard_LRS
   az storage container create --name resumes --account-name saairesumes
   ```
2. Add connection string to `.env`:
   ```env
   AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=saairesumes;AccountKey=...;EndpointSuffix=core.windows.net"
   AZURE_STORAGE_CONTAINER="resumes"
   ```

### Stage 3: Azure Functions (Serverless Worker)
The `azure_functions/` directory contains an Azure Function App with:
- **`screen_resume_http`**: HTTP endpoint (`POST /api/screen_resume`) for serverless parsing & scoring.
- **`resume_blob_trigger`**: Event-driven trigger that wakes up whenever a resume PDF is uploaded to Blob Storage.

Deploying to Azure:
```powershell
cd azure_functions
func azure functionapp publish func-ai-resume-screener
```

### Stage 4: Azure OpenAI Semantic Matching
1. Create an Azure OpenAI resource in the Azure Portal.
2. Deploy the `text-embedding-3-small` or `text-embedding-ada-002` embedding model.
3. Configure the endpoint and key in `.env`:
   ```env
   AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
   AZURE_OPENAI_KEY="your-api-key"
   AZURE_OPENAI_DEPLOYMENT="text-embedding-3-small"
   ```

### Stage 5: Deploy Flask to Azure App Service
Deploy in one click using PowerShell:
```powershell
.\deploy.ps1 -ResourceGroup "rg-ai-resume" -AppName "ai-resume-screener"
```
Or using the production `Dockerfile` with Azure Container Apps / Web App for Containers:
```powershell
docker build -t ai-resume-screener .
az webapp create --resource-group rg-ai-resume --plan asp-ai-resume --name ai-resume-screener --deployment-container-image-name ai-resume-screener
```

---

## 📊 Explainable Multi-Factor Scoring Model

The composite score balances rule-based precision with neural semantic understanding:

$$\text{Overall Score} = (0.40 \times \text{Skill Score}) + (0.20 \times \text{Semantic AI Score}) + (0.20 \times \text{Experience Score}) + (0.20 \times \text{Education Score})$$

- **Skill Score (40%)**: Ratio of matched required skills against candidate skills with canonical alias expansion across 45+ technical clusters.
- **Semantic AI Score (20%)**: High-dimensional cosine similarity between Job Description context and Resume text (via Azure OpenAI or local TF-IDF vector space).
- **Experience Score (20%)**: Proportional scaling up to required years of experience ($\min(100, \frac{\text{Years}}{\text{Required}} \times 100)$).
- **Education Score (20%)**: Degree hierarchy validation (Ph.D, M.Tech, B.Tech, MCA, BCA, etc.).

```

---

## 🌟 Key Features & Azure Architecture

The platform implements the complete 5-stage Azure Cloud Architecture:

| # | Architecture Stage | Implementation Details | Cloud Component | Local Fallback |
|---|---|---|---|---|
| **1** | **Database Storage** | Replaced SQLite with unified DB layer supporting Azure SQL Database | `Azure SQL / ODBC Driver 18` | SQLite (`resume_screening.db`) |
| **2** | **Resume Storage** | Uploads candidate resumes to secure blob containers | `Azure Blob Storage` (`resumes`) | Local Filesystem (`uploads/`) |
| **3** | **Serverless Workers** | Serverless PDF ingestion & asynchronous parsing pipeline | `Azure Functions (Python v2)` | In-App Extraction Pipeline |
| **4** | **Semantic AI Matching** | Contextual relevance scoring with neural embeddings | `Azure OpenAI Embeddings` | Domain TF-IDF Vectorizer |
| **5** | **Cloud Deployment** | Production containerization & automated cloud hosting | `Azure App Service (Linux Web App)` | Localhost (`5000`) |

---

## 🚀 Quickstart: Run Locally

### 1. Prerequisites & Virtual Environment
```powershell
# Create and activate virtual environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install production dependencies
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
*(If no Azure credentials are provided in `.env`, the system runs in offline/local fallback mode automatically).*

### 3. Start the Application
```powershell
python app.py
```
Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser.

---

## ☁️ Azure Cloud Deployment (Stage by Stage)

### Stage 1: Azure SQL Database Setup
1. Provision Azure SQL Server & Database in the Azure Portal or via Azure CLI:
   ```powershell
   az sql server create --name sql-airesume --resource-group rg-ai-resume --location eastus --admin-user cloudadmin --admin-password "YourStrongPassword!"
   az sql db create --resource-group rg-ai-resume --server sql-airesume --name resume_screening_db --service-objective Basic
   ```
2. Set the connection string in your `.env` or App Service configuration:
   ```env
   AZURE_SQL_CONNECTION_STRING="Driver={ODBC Driver 18 for SQL Server};Server=tcp:sql-airesume.database.windows.net,1433;Database=resume_screening_db;Uid=cloudadmin;Pwd=YourStrongPassword!;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
   ```

### Stage 2: Azure Blob Storage Setup
1. Create storage account and blob container:
   ```powershell
   az storage account create --name saairesumes --resource-group rg-ai-resume --location eastus --sku Standard_LRS
   az storage container create --name resumes --account-name saairesumes
   ```
2. Add connection string to `.env`:
   ```env
   AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=saairesumes;AccountKey=...;EndpointSuffix=core.windows.net"
   AZURE_STORAGE_CONTAINER="resumes"
   ```

### Stage 3: Azure Functions (Serverless Worker)
The `azure_functions/` directory contains an Azure Function App with:
- **`screen_resume_http`**: HTTP endpoint (`POST /api/screen_resume`) for serverless parsing & scoring.
- **`resume_blob_trigger`**: Event-driven trigger that wakes up whenever a resume PDF is uploaded to Blob Storage.

Deploying to Azure:
```powershell
cd azure_functions
func azure functionapp publish func-ai-resume-screener
```

### Stage 4: Azure OpenAI Semantic Matching
1. Create an Azure OpenAI resource in the Azure Portal.
2. Deploy the `text-embedding-3-small` or `text-embedding-ada-002` embedding model.
3. Configure the endpoint and key in `.env`:
   ```env
   AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
   AZURE_OPENAI_KEY="your-api-key"
   AZURE_OPENAI_DEPLOYMENT="text-embedding-3-small"
   ```

### Stage 5: Deploy Flask to Azure App Service
Deploy in one click using PowerShell:
```powershell
.\deploy.ps1 -ResourceGroup "rg-ai-resume" -AppName "ai-resume-screener"
```
Or using the production `Dockerfile` with Azure Container Apps / Web App for Containers:
```powershell
docker build -t ai-resume-screener .
az webapp create --resource-group rg-ai-resume --plan asp-ai-resume --name ai-resume-screener --deployment-container-image-name ai-resume-screener
```

---

## 📊 Explainable Multi-Factor Scoring Model

The composite score balances rule-based precision with neural semantic understanding:

$$\text{Overall Score} = (0.40 \times \text{Skill Score}) + (0.20 \times \text{Semantic AI Score}) + (0.20 \times \text{Experience Score}) + (0.20 \times \text{Education Score})$$

- **Skill Score (40%)**: Ratio of matched required skills against candidate skills with canonical alias expansion across 45+ technical clusters.
- **Semantic AI Score (20%)**: High-dimensional cosine similarity between Job Description context and Resume text (via Azure OpenAI or local TF-IDF vector space).
- **Experience Score (20%)**: Proportional scaling up to required years of experience ($\min(100, \frac{\text{Years}}{\text{Required}} \times 100)$).
- **Education Score (20%)**: Degree hierarchy validation (Ph.D, M.Tech, B.Tech, MCA, BCA, etc.).