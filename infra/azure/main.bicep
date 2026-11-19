// Clinical Event Stream landing zone: one ADLS Gen2 account with a filesystem
// per layer, and a budget that mails me at $1. Deployed into a resource group.
//
//   az deployment group create -g rg-clinical-event-stream -f main.bicep \
//      -p storageAccountName=<globally unique, 3-24 lowercase alphanumerics> alertEmail=<me>

@minLength(3)
@maxLength(24)
param storageAccountName string
param alertEmail string
param location string = resourceGroup().location

// Monthly budget in USD. The free account has $200 of credit for 30 days and
// 5 GB of LRS blob storage for 12 months; this project should cost nothing.
param budgetAmount int = 1

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    isHnsEnabled: true                 // hierarchical namespace = ADLS Gen2
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
    networkAcls: { defaultAction: 'Allow', bypass: 'AzureServices' }
  }
  tags: { project: 'clinical-event-stream', data: 'synthetic' }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

// One filesystem per layer so each can carry its own RBAC. Bronze holds
// identified (synthetic) rows and would get the narrowest reader set.
var layers = ['bronze', 'silver', 'gold', 'published']
resource filesystems 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for layer in layers: {
  parent: blobService
  name: layer
  properties: { publicAccess: 'None' }
}]

// Lifecycle: bronze cohorts older than 90 days move to cool; nothing is deleted.
resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'cool-old-bronze'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: { blobTypes: ['blockBlob'], prefixMatch: ['bronze/'] }
            actions: { baseBlob: { tierToCool: { daysAfterModificationGreaterThan: 90 } } }
          }
        }
      ]
    }
  }
}

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'clinical-event-stream-monthly'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: '${substring(utcNow(), 0, 7)}-01'
    }
    notifications: {
      actual80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [alertEmail]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [alertEmail]
      }
    }
  }
}

output storageAccount string = storage.name
output dfsEndpoint string = storage.properties.primaryEndpoints.dfs
