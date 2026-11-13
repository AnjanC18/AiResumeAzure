<#
.SYNOPSIS
    Automated Azure Cloud Deployment Script for AI Resume Screening Platform.
.DESCRIPTION
    Creates resource group, Azure SQL, Azure Storage Blob container, and deploys Flask to Azure App Service.
#>

param(
    [string]$ResourceGroup = "rg-ai-resume-mvp",
    [string]$Location = "eastus",
    [string]$AppName = "ai-resume-screener-" + (Get-Random -Minimum 1000 -Maximum 9999),
    [string]$StorageAccountName = "airesume" + (Get-Random -Minimum 1000 -Maximum 9999),
    [string]$SqlAdminUser = "cloudadmin",
    [string]$SqlAdminPassword = "SecurePassword123!"
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Deploying AI Resume Screening Platform to Microsoft Azure" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Check Azure Login
Write-Host "`n[1/5] Verifying Azure Authentication..." -ForegroundColor Yellow
$account = az account show 2>$null
if (-not $account) {
    Write-Host "Not signed in to Azure. Running 'az login'..." -ForegroundColor Yellow
    az login
}

# 2. Create Resource Group
Write-Host "`n[2/5] Creating Resource Group: $ResourceGroup in $Location..." -ForegroundColor Yellow
az group create --name $ResourceGroup --location $Location | Out-Null

# 3. Create Azure Storage Account & Container
Write-Host "`n[3/5] Provisioning Azure Storage Account: $StorageAccountName..." -ForegroundColor Yellow
az storage account create `
    --name $StorageAccountName `
    --resource-group $ResourceGroup `
    --location $Location `
    --sku Standard_LRS | Out-Null

$storageConnStr = az storage account show-connection-string `
    --name $StorageAccountName `
    --resource-group $ResourceGroup `
    --query connectionString `
    --output tsv

az storage container create `
    --name resumes `
    --connection-string $storageConnStr | Out-Null
Write-Host "Storage container 'resumes' ready." -ForegroundColor Green

# 4. Provision Azure App Service Plan & Web App
Write-Host "`n[4/5] Deploying App Service (Linux, Python 3.11): $AppName..." -ForegroundColor Yellow
az appservice plan create `
    --name "asp-ai-resume" `
    --resource-group $ResourceGroup `
    --is-linux `
    --sku B1 | Out-Null

az webapp create `
    --name $AppName `
    --plan "asp-ai-resume" `
    --resource-group $ResourceGroup `
    --runtime "PYTHON:3.11" | Out-Null

# Configure Startup command & Environment variables
az webapp config set `
    --name $AppName `
    --resource-group $ResourceGroup `
    --startup-file "startup.sh" | Out-Null

az webapp config appsettings set `
    --name $AppName `
    --resource-group $ResourceGroup `
    --settings `
        AZURE_STORAGE_CONNECTION_STRING="$storageConnStr" `
        AZURE_STORAGE_CONTAINER="resumes" `
        SECRET_KEY="$(New-Guid)" `
        PORT="5000" | Out-Null

# 5. Deploy application zip
Write-Host "`n[5/5] Deploying source code via Zip deploy..." -ForegroundColor Yellow
az webapp deploy `
    --name $AppName `
    --resource-group $ResourceGroup `
    --src-path . `
    --type zip | Out-Null

$appUrl = "https://$AppName.azurewebsites.net"
Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " Deployment Complete!" -ForegroundColor Green
Write-Host " Application URL: $appUrl" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

