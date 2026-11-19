# Creates the Azure landing zone and prints the two values the pipeline needs.
# Run once, signed in with `az login` on the free account.
#
#   .\infra\azure\deploy.ps1 -StorageAccountName cesjagadish001 -AlertEmail me@example.com
#
# Then store the outputs as GitHub secrets so the weekly workflow lands the layers:
#   gh secret set CES_AZURE_STORAGE_ACCOUNT --body <account>
#   gh secret set CES_AZURE_STORAGE_KEY     --body <key>
param(
    [Parameter(Mandatory = $true)][string]$StorageAccountName,
    [Parameter(Mandatory = $true)][string]$AlertEmail,
    [string]$ResourceGroup = "rg-clinical-event-stream",
    [string]$Location = "eastus2"
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

az account show --output none
az group create --name $ResourceGroup --location $Location --output none
az deployment group create `
    --resource-group $ResourceGroup `
    --template-file (Join-Path $here "main.bicep") `
    --parameters storageAccountName=$StorageAccountName alertEmail=$AlertEmail `
    --output table

$key = az storage account keys list --resource-group $ResourceGroup --account-name $StorageAccountName --query "[0].value" --output tsv
Write-Host ""
Write-Host "CES_AZURE_STORAGE_ACCOUNT=$StorageAccountName"
Write-Host "CES_AZURE_STORAGE_KEY=<printed below once; store it as a secret, never in the repo>"
Write-Host $key
Write-Host ""
Write-Host "Local landing:  `$env:CES_TARGET='azure'; `$env:CES_AZURE_STORAGE_ACCOUNT='$StorageAccountName'; `$env:CES_AZURE_STORAGE_KEY='<key>'; .\.venv\Scripts\python -m ces land"
