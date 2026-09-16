#Requires -Version 7.4
#Requires -Modules PnP.PowerShell
[CmdletBinding(SupportsShouldProcess)]
param(
  [Parameter(Mandatory)][uri]$SiteUrl,
  [Parameter(Mandatory)][string]$ClientId,
  [string]$ListTitle = 'ALEX - Dossiers'
)
$ErrorActionPreference = 'Stop'
# Interactive login uses an enterprise-approved Entra application, not a password in a file.
$connection = Connect-PnPOnline -Url $SiteUrl.AbsoluteUri -ClientId $ClientId -Interactive -ReturnConnection
$list = Get-PnPList -Identity $ListTitle -Connection $connection -ErrorAction SilentlyContinue
if (!$PSCmdlet.ShouldProcess($SiteUrl, "Créer/configurer la liste ALEX et ses groupes")) { return }
if (!$list) {
  $list = New-PnPList -Title $ListTitle -Url 'Lists/AlexDossiers' -Template GenericList -EnableVersioning -Connection $connection
}
Set-PnPList -Identity $list.Id -EnableVersioning $true -MajorVersions 500 -EnableAttachments $false -Connection $connection | Out-Null
$schema = Get-Content (Join-Path $PSScriptRoot 'schema.json') -Raw | ConvertFrom-Json
foreach ($field in $schema.fields) {
  $existing = Get-PnPField -List $list.Id -Identity $field.name -Connection $connection -ErrorAction SilentlyContinue
  if ($existing) {
    if ($existing.TypeAsString -ne $field.type) { throw "Colonne $($field.name) incompatible : $($existing.TypeAsString), attendu $($field.type). Aucune conversion automatique." }
  } else {
    $name = [System.Security.SecurityElement]::Escape($field.name)
    $label = [System.Security.SecurityElement]::Escape($field.label)
    $options = ''
    if ($field.type -eq 'Choice') {
      $options = '<CHOICES>' + (($field.choices | ForEach-Object { '<CHOICE>' + [System.Security.SecurityElement]::Escape($_) + '</CHOICE>' }) -join '') + '</CHOICES>'
    }
    $extra = if ($field.type -eq 'Note') { ' RichText="FALSE" AppendOnly="FALSE" NumLines="6"' } else { '' }
    $xml = "<Field Type=`"$($field.type)`" Name=`"$name`" StaticName=`"$name`" DisplayName=`"$label`"$extra>$options</Field>"
    Add-PnPFieldFromXml -List $list.Id -FieldXml $xml -Connection $connection | Out-Null
  }
  if ($field.indexed) { Set-PnPField -List $list.Id -Identity $field.name -Values @{Indexed=$true} -Connection $connection | Out-Null }
}
Set-PnPField -List $list.Id -Identity 'AlexKey' -Values @{Indexed=$true;EnforceUniqueValues=$true;Required=$true} -Connection $connection | Out-Null
# Preserve site administrators / owners, remove inherited broad membership on this NEW application list.
# Do not remove pre-existing unique permissions when rerun; review the ACL before production.
$list = Get-PnPList -Identity $list.Id -Includes HasUniqueRoleAssignments -Connection $connection
if (!$list.HasUniqueRoleAssignments) { Set-PnPList -Identity $list.Id -BreakRoleInheritance -CopyRoleAssignments:$false -Connection $connection | Out-Null }
$roles = Get-PnPRoleDefinition -Connection $connection
$contribute = $roles | Where-Object { $_.RoleTypeKind -eq 'Contributor' } | Select-Object -First 1
if (!$contribute) { throw 'Niveau de permission Contribution introuvable.' }
foreach ($name in @('ALEX Analystes','ALEX Managers','ALEX Deontologie')) {
  $group = Get-PnPGroup -Identity $name -Connection $connection -ErrorAction SilentlyContinue
  if (!$group) { $group = New-PnPGroup -Title $name -Description 'Accès ALEX. Membres directs gérés par le propriétaire du site.' -Connection $connection }
  Set-PnPListPermission -Identity $list.Id -Group $group.Id -AddRole $contribute.Name -Connection $connection
}
foreach ($view in $schema.views) {
  $existing = Get-PnPView -List $list.Id -Identity $view.title -Connection $connection -ErrorAction SilentlyContinue
  if (!$existing) { Add-PnPView -List $list.Id -Title $view.title -Fields @('LinkTitle','AlexClient','AlexType','AlexStatus','AlexPriority','AlexAnalyst','Modified','Editor') -Query $view.query -RowLimit 100 -Paged -Connection $connection | Out-Null }
}
Write-Host 'Liste prête. Ajouter les membres directs aux trois groupes ALEX et leur donner accès à la page SharePoint.'
Write-Host 'Les groupes disposent de Contribution sur la liste : les contrôles par rôle de l’application ne sont pas une sécurité serveur par colonne.'
[pscustomobject]@{ SiteUrl=$SiteUrl.AbsoluteUri; ListTitle=$ListTitle; ListId=$list.Id.ToString(); Component='ALEX – Sécurité financière' } | ConvertTo-Json
