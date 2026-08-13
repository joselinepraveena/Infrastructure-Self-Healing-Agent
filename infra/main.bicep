targetScope = 'resourceGroup'

@description('Globally unique prefix used for deployed resource names.')
@minLength(3)
@maxLength(12)
param namePrefix string

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Keep true until sandbox tests and approvals are complete.')
param dryRun bool = true

@description('Comma-separated resource Environment tag values eligible for healing.')
param allowedEnvironments string = 'dev,test,staging'

@description('Maximum remediation attempts per resource in the cooldown window.')
@minValue(1)
param maxAttempts int = 1

@description('Cooldown window used for retry limiting.')
@minValue(1)
param cooldownMinutes int = 30

var suffix = uniqueString(subscription().subscriptionId, resourceGroup().id)
var functionName = '${namePrefix}-heal-${suffix}'
var storageName = 'sh${suffix}'
var blobDataOwnerRole = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
)
var queueDataContributorRole = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
)
var storageAccountContributorRole = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '17d1049b-9a84-46fb-8f53-869881c3d3ab'
)
var tableDataContributorRole = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
)

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-heal-logs'
  location: location
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-heal-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${namePrefix}-heal-plan'
  location: location
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storage.name
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: insights.properties.ConnectionString
        }
        {
          name: 'STATE_STORAGE_ACCOUNT_URL'
          value: 'https://${storage.name}.table.${environment().suffixes.storage}'
        }
        {
          name: 'DRY_RUN'
          value: string(dryRun)
        }
        {
          name: 'ALLOWED_ENVIRONMENTS'
          value: allowedEnvironments
        }
        {
          name: 'MAX_ATTEMPTS'
          value: string(maxAttempts)
        }
        {
          name: 'COOLDOWN_MINUTES'
          value: string(cooldownMinutes)
        }
      ]
    }
  }
}

resource blobAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, blobDataOwnerRole)
  scope: storage
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: blobDataOwnerRole
  }
}

resource queueAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, queueDataContributorRole)
  scope: storage
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: queueDataContributorRole
  }
}

resource storageAccountAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, storageAccountContributorRole)
  scope: storage
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: storageAccountContributorRole
  }
}

resource tableAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, tableDataContributorRole)
  scope: storage
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: tableDataContributorRole
  }
}

resource remediationRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'self-healing-app-service-restart')
  properties: {
    roleName: '${namePrefix} App Service Restarter'
    description: 'Read resource metadata and restart explicitly opted-in App Services.'
    type: 'CustomRole'
    permissions: [
      {
        actions: [
          'Microsoft.Resources/subscriptions/resourceGroups/read'
          'Microsoft.Resources/subscriptions/resourceGroups/resources/read'
          'Microsoft.Web/sites/read'
          'Microsoft.Web/sites/restart/action'
        ]
        notActions: []
      }
    ]
    assignableScopes: [
      resourceGroup().id
    ]
  }
}

resource remediationAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, functionApp.id, remediationRole.id)
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: remediationRole.id
  }
}

output functionAppName string = functionApp.name
output functionResourceId string = functionApp.id
output alertFunctionName string = 'HandleMonitorAlert'
output stateStorageAccountName string = storage.name
