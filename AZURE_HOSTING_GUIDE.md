# End-to-End Azure Cloud Hosting Guide
## AI-Powered Resume Screening & Candidate Ranking Platform

This guide provides a comprehensive, click-by-click manual to host the entire AI Resume Screening platform on **Microsoft Azure**.

---

## 🏛️ Architecture Overview

The deployed system consists of 4 main cloud services hosted within a single Resource Group:

```mermaid
flowchart TD
    User(["Recruiter / User Browser"]) -->|HTTPS Request| AppService["Azure App Service (Linux, Python 3.11)\nFlask + Gunicorn WSGI"]
    
    subgraph AzureCloud ["Microsoft Azure Cloud (rg-ai-resume)"]
        AppService -->|1. Store Resumes (PDF)| Blob["Azure Blob Storage\nContainer: 'resumes'"]
        AppService -->|2. Relational Data (Jobs/Candidates)| SQL["Azure SQL Database\nresume_screening_db"]
        AppService -.->|3. Vector Embeddings (Optional)| OpenAI["Azure OpenAI Service\ntext-embedding-3-small"]
        Blob -.->|4. Event Trigger (Async)| Func["Azure Function App\nPython v2 Worker"]
        Func -.->|Update Screening Scores| SQL
    end

    classDef primary fill:#4f46e5,stroke:#4338ca,stroke-width:2px,color:#fff;
    classDef cloud fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#fff;
    classDef storage fill:#059669,stroke:#047857,stroke-width:2px,color:#fff;
    
    class AppService primary;
    class Blob,SQL,OpenAI storage;
    class Func cloud;
```

---

## 📋 Pre-Flight Checklist & Cost Optimization

Before you begin, ensure you have:
1. An active [Microsoft Azure Account](https://azure.microsoft.com/) (Free Trial includes $200 credits for 30 days + 12 months of popular free services).
2. Git installed on your computer.
3. Access to [Azure Portal](https://portal.azure.com/).

> [!TIP] Cost Optimization Tip
> - **Azure SQL**: Select **Service Tier: Basic** (5 DTUs, ~$4.99/month) or Serverless with 1-hour auto-pause.
> - **Blob Storage**: Select **Standard LRS** (Locally Redundant Storage), costing only pennies per gigabyte.
> - **App Service**: Use the **Free (F1)** tier for student/demo use, or **Basic (B1)** (~$13/month) if you need custom domains or "Always On".

---

## Phase 1: Create the Azure Resource Group

The Resource Group acts as a folder containing all related project services for easy management and billing tracking.

1. Sign in to the [Azure Portal](https://portal.azure.com).
2. In the top global search bar, type **Resource groups** and select it.
3. Click **+ Create** (or **Create resource group**).
4. Fill in the basics:
   - **Subscription**: Select your active subscription.
   - **Resource group**: `rg-ai-resume`
   - **Region**: Choose a region close to your target audience (e.g., `East US`, `Central India`, or `West Europe`).
5. Click **Review + create**, then click **Create**.

---

## Phase 2: Create Azure Blob Storage (For Resume PDFs)

Resumes will be securely uploaded and streamed directly to an Azure Blob Storage container instead of local disk.

### 2.1 Provision the Storage Account
1. Search for **Storage accounts** in the top search bar &rarr; click **+ Create**.
2. On the **Basics** tab:
   - **Resource group**: Select `rg-ai-resume`.
   - **Storage account name**: Enter a unique lowercase name with only letters and numbers (e.g., `airesume` + your initials + random digits, e.g., `airesumestorage101`).
   - **Region**: Same region as your resource group (e.g., `East US`).
   - **Performance**: `Standard`.
   - **Redundancy**: Select `Locally-redundant storage (LRS)` (lowest cost).
3. Click **Review**, then click **Create**. Wait ~1 minute for deployment to finish.

### 2.2 Create the `resumes` Container
1. Click **Go to resource** (or navigate to your newly created Storage account).
2. In the left-hand navigation under **Data storage**, click **Containers**.
3. Click **+ Container** at the top:
   - **Name**: `resumes` (must be exact).
   - **Anonymous access level**: Select **Blob (anonymous read access for blobs only)** or **Private** (recommended).
4. Click **Create**.

### 2.3 Copy the Storage Connection String
1. In the left sidebar under **Security + networking**, click **Access keys**.
2. Click the **Show** button next to **Connection string** under `key1`.
3. Click the copy icon to save this string. It has the format:
   ```text
   DefaultEndpointsProtocol=https;AccountName=airesumestorage101;AccountKey=...==;EndpointSuffix=core.windows.net
   ```
   *(Keep this copied for your environment variables later).*

---

## Phase 3: Create Azure SQL Database

Stores jobs, candidates, and AI screening analytics in a high-availability relational database.

### 3.1 Provision SQL Server & Database
1. Search for **SQL databases** &rarr; click **+ Create**.
2. On the **Basics** tab:
   - **Resource group**: `rg-ai-resume`
   - **Database name**: `resume_screening_db`
   - **Server**: Click **Create new** just below the server dropdown:
     - **Server name**: e.g., `sql-airesume-server-101` (must be globally unique).
     - **Location**: Same region as your resource group.
     - **Authentication method**: Select **Use SQL authentication** (or SQL and Microsoft Entra).
     - **Server admin login**: `cloudadmin`
     - **Password**: Enter a strong password (e.g., `P@ssw0rd1234!#`).
     - Click **OK**.
   - **Workload environment**: Select `Development`.
   - **Compute + storage**: Click **Configure database**:
     - Switch to **DTU-based purchasing options** &rarr; select **Basic** (5 DTUs, 2 GB storage, ~$5/month).
     - *(Alternatively, choose General Purpose Serverless with minimum 0.5 vCore and auto-pause enabled).*
     - Click **Apply**.
   - **Backup storage redundancy**: `Locally-redundant backup storage`.

### 3.2 Configure SQL Firewall Rules (Critical Step!)
1. Click the **Networking** tab at the top of the SQL Database creation screen:
   - **Connectivity method**: `Public endpoint`.
   - **Allow Azure services and resources to access this server**: Select **Yes** *(allows Azure App Service to connect)*.
   - **Add current client IP address**: Select **Yes** *(allows your local computer to connect for migrations and testing)*.
2. Click **Review + create**, then click **Create**. Deployment takes 2–3 minutes.

### 3.3 Get the ODBC Connection String
1. Go to your `resume_screening_db` resource.
2. In the left sidebar under **Settings**, click **Connection strings**.
3. Select the **ODBC** tab.
4. Copy the string. It will look like this:
   ```text
   Driver={ODBC Driver 18 for SQL Server};Server=tcp:sql-airesume-server-101.database.windows.net,1433;Database=resume_screening_db;Uid=cloudadmin;Pwd={your_password_here};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;
   ```
5. Replace `{your_password_here}` with the actual password you created in Step 3.1.

---

## Phase 4: Create Azure App Service (Web App)

Hosts your Flask application and serves the recruiter dashboard with high availability and automated SSL.

1. In the portal, search for **App Services** &rarr; click **+ Create** &rarr; select **Web App**.
2. On the **Basics** tab:
   - **Subscription**: Your active subscription.
   - **Resource Group**: `rg-ai-resume`.
   - **Name**: e.g., `talentai-screening-app` (Your app will be live at `https://<name>.azurewebsites.net`).
   - **Publish**: `Code`.
   - **Runtime stack**: **Python 3.11**.
   - **Operating System**: **Linux**.
   - **Region**: Same region as your resource group.
   - **Pricing Plan**:
     - For testing: Select **Free F1** (60 CPU minutes/day).
     - For production: Select **Basic B1** (Always On, SSL, dedicated compute).
3. Click **Review + create**, then click **Create**. Wait ~1 minute.

---

## Phase 5: Configure App Service Environment Variables & Startup Command

Before deploying the code, configure the environment variables so Flask connects to Azure SQL and Azure Blob Storage.

### 5.1 Add Application Settings (Environment Variables)
1. Go to your newly created Web App resource.
2. In the left navigation, under **Settings**, click **Environment variables** (or **Configuration** in older UI).
3. Under the **App settings** tab, click **+ Add** for each of the following key-value pairs:

| Name / Key | Value | Purpose |
|---|---|---|
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `1` | Forces Azure Oryx to run `pip install -r requirements.txt` during build |
| `SECRET_KEY` | *(A random string, e.g. `d7a6b9c8e1f2038475628192`)* | Secures Flask session cookies |
| `FLASK_DEBUG` | `False` | Disables debug mode in production |
| `AZURE_SQL_CONNECTION_STRING` | *(The ODBC connection string from Phase 3.3)* | Connects to Azure SQL Database |
| `AZURE_STORAGE_CONNECTION_STRING` | *(The Blob connection string from Phase 2.3)* | Connects to Azure Blob Storage |
| `AZURE_STORAGE_CONTAINER` | `resumes` | Name of the target container |
| `PORT` | `8000` | Port for Gunicorn WSGI server |

4. Click **Apply** (or **Save**) and confirm the restart.

### 5.2 Set the Startup Command
1. In the same **Settings** section, click on **Configuration** (or **General settings** under Environment variables).
2. Look for the **Startup Command** field.
3. Enter:
   ```bash
   startup.sh
   ```
   *(Or alternatively: `gunicorn --bind=0.0.0.0:8000 --workers=2 --timeout=120 app:app`)*.
4. Click **Save** and confirm.

---

## Phase 6: Deploy Code to Azure App Service

You can deploy using any of the three methods below. **Method A (GitHub Actions)** is the recommended industry standard.

### Method A: Automated Deployment via GitHub Actions (Recommended)

1. Push your project to a GitHub repository:
   ```powershell
   git add .
   git commit -m "Configure production Azure Cloud deployment"
   git push origin main
   ```
2. In the Azure Portal, navigate to your Web App &rarr; left sidebar **Deployment Center**.
3. Under **Settings**:
   - **Source**: Select **GitHub**.
   - Authenticate with your GitHub account if prompted.
   - **Organization**: Your GitHub username.
   - **Repository**: Select your repo (e.g., `ai_resume_screening_mvp` or `AiResumeAzure`).
   - **Branch**: `main`.
4. Click **Save** at the top.
   - Azure will automatically commit a GitHub Actions workflow file to your repo and trigger the initial build and deployment.
5. In your GitHub repository, click the **Actions** tab to watch the workflow build and deploy your app in real-time.

---

### Method B: Deploy from VS Code (Quick & Direct)

1. Open your project folder in **Visual Studio Code**.
2. Install the **Azure App Service** extension (by Microsoft) from the Extensions marketplace.
3. Click the **Azure** icon in the VS Code sidebar &rarr; sign in to your Azure account.
4. Expand your subscription &rarr; **App Services** &rarr; find your Web App (`talentai-screening-app`).
5. **Right-click** on the Web App name &rarr; select **Deploy to Web App...**.
6. Select your project root folder when prompted.
7. Click **Deploy** in the confirmation popup.

---

### Method C: One-Click CLI Zip Deployment (Using PowerShell)

If you have Azure CLI installed:
1. Open PowerShell in the project directory:
   ```powershell
   # 1. Login to Azure
   az login

   # 2. Deploy directly via CLI
   az webapp deploy --resource-group rg-ai-resume --name talentai-screening-app --src-path . --type zip
   ```

---

## Phase 7: Verification & Testing

1. In the Azure Portal, go to your Web App Overview page.
2. Click on the **Default domain** link (e.g., `https://talentai-screening-app.azurewebsites.net`).
3. Verify the **Azure Cloud Architecture Ribbon** at the top of the page:
   - **Azure SQL Database**: Connected
   - **Azure Blob Storage**: Connected (`resumes`)
   - **Semantic NLP Engine**: Active
4. Test the workflow:
   - Click **Post New Job** &rarr; create a sample requisition (e.g., *Full Stack Python Developer*).
   - Click **Upload Resumes** &rarr; upload a PDF resume from `sample_resumes/`.
   - Confirm that the resume appears in the candidate table with parsed skills, experience, education, and composite scores.
   - Click **Details** &rarr; verify the **Azure Blob** link opens the uploaded PDF from cloud storage.

---

## Phase 8: Deploy Azure Functions (Optional Async Serverless Trigger)

If you wish to run document extraction in a dedicated serverless environment:

1. In the portal, search for **Function App** &rarr; click **+ Create**.
2. Settings:
   - **Hosting plan**: `Consumption (Serverless)` (First 1 million executions/month are free).
   - **Runtime stack**: `Python 3.11`.
   - **Operating System**: `Linux`.
   - **Storage account**: Select the storage account created in Phase 2 (`airesumestorage101`).
3. Deploy the function app from your terminal using Azure Functions Core Tools:
   ```powershell
   cd azure_functions
   func azure functionapp publish <your-function-app-name>
   ```

---

## 🛠️ Troubleshooting & Common Gotchas

### 1. Web App shows "Application Error" or 503
- **Check Live Logs**: In Azure Portal, go to your Web App &rarr; in left menu under **Monitoring**, click **Log stream**.
- **Common Cause**: Python package build failed. Ensure `SCM_DO_BUILD_DURING_DEPLOYMENT = 1` is set in Environment variables.

### 2. Database Connection Error (`Login failed` or `Cannot open server`)
- **Check Firewall**: Ensure in Azure SQL Server &rarr; **Networking**, "Allow Azure services and resources to access this server" is checked **Yes**.
- **ODBC Driver**: Linux App Service uses `{ODBC Driver 18 for SQL Server}`. Ensure `Encrypt=yes;TrustServerCertificate=no;` is present in the connection string.

### 3. Uploaded PDFs fail to upload or show 404
- **Check Storage Container**: Verify container name is exactly `resumes` in your Storage account.
- **Check Connection String**: Verify the `AZURE_STORAGE_CONNECTION_STRING` contains `DefaultEndpointsProtocol=https;...`.

---

## 🏁 Summary Checklist

- [ ] Resource Group `rg-ai-resume` created
- [ ] Storage Account + `resumes` blob container created
- [ ] Azure SQL Server + `resume_screening_db` created (Basic Tier)
- [ ] SQL Firewall rule enabled for Azure Services
- [ ] App Service (Linux, Python 3.11) created
- [ ] App Settings (`SCM_DO_BUILD_DURING_DEPLOYMENT`, connection strings) added
- [ ] Startup command `startup.sh` configured
- [ ] Code deployed via GitHub Actions or VS Code
- [ ] End-to-end PDF resume upload verified on live URL

