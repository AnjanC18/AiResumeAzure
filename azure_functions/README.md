# Azure Functions - Serverless Resume Screening Worker

This directory contains the Azure Functions (Python v2 programming model) implementation for offloading PDF document parsing, entity extraction, and candidate scoring to a serverless architecture.

## Functions Included

1. **`screen_resume_http` (HTTP Trigger)**
   - Route: `POST /api/screen_resume`
   - Accepts either JSON payload with resume text or multipart/binary PDF streams.
   - Returns structured candidate attributes and calculated scoring metrics.

2. **`resume_blob_trigger` (Blob Trigger)**
   - Listens on the Azure Blob Storage container: `resumes/{name}`
   - Automatically executes whenever a new resume PDF is uploaded to Blob Storage.
   - Extracts text, parses contact info & skills, computes match scores, and writes records into Azure SQL Database.

## Running Locally

1. Install Azure Functions Core Tools v4:
   ```powershell
   npm install -g azure-functions-core-tools@4 --unsafe-perm true
   ```
2. Start Azurite local storage emulator (or provide an actual Azure Storage connection string in `local.settings.json`).
3. Start the function app locally:
   ```powershell
   cd azure_functions
   func start
   ```

## Deploying to Azure

```powershell
# Create resource group and storage account (if not existing)
az group create --name rg-ai-resume --location eastus
az storage account create --name saairesumes --resource-group rg-ai-resume --sku Standard_LRS

# Create Azure Function App (Consumption Plan)
az functionapp create --resource-group rg-ai-resume --consumption-plan-location eastus --runtime python --runtime-version 3.11 --functions-version 4 --name func-ai-resume-screener --storage-account saairesumes --os-type linux

# Publish function code
func azure functionapp publish func-ai-resume-screener
```

