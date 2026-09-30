$ErrorActionPreference = 'Stop'
$planDirectory = Split-Path -Parent $PSCommandPath
$scopeRoot = [IO.Path]::GetFullPath('D:\ChatGPT\Mobile ESS 2').TrimEnd('\')
$rows = Import-Csv -LiteralPath (Join-Path $planDirectory 'WINDOWS_SAFE_DELETE_MANIFEST.csv')
$deleted = @()
foreach ($row in $rows) {
    if ($row.classification -ne 'SAFE_DELETE_REDUNDANT' -or $row.delete_approved -ne 'True') { continue }
    $resolvedTarget = (Resolve-Path -LiteralPath $row.path).Path.TrimEnd('\')
    if (-not $resolvedTarget.StartsWith($scopeRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Target outside approved scope: $resolvedTarget" }
    if ($resolvedTarget -match '(?i)ieee[_-]?8500|8500[-_ ]?node|[\\/]WSL([\\/]|$)') { throw "Protected target: $resolvedTarget" }
    $targetItem = Get-Item -LiteralPath $resolvedTarget
    if ($targetItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse target cannot be removed: $resolvedTarget" }
    $actualFiles = @(Get-ChildItem -LiteralPath $resolvedTarget -Recurse -File -Force)
    $actualBytes = ($actualFiles | Measure-Object -Property Length -Sum).Sum
    if ($actualBytes -ne [long]$row.bytes -or $actualFiles.Count -ne [long]$row.file_count) { throw "Target changed since inventory: $resolvedTarget" }
    $targetHead = git -C $resolvedTarget rev-parse HEAD
    if ($targetHead -ne $row.Git_authority) { throw "Git authority changed: $resolvedTarget" }
    $targetStatus = git -C $resolvedTarget status --porcelain=v1
    if ($targetStatus) { throw "Dirty target: $resolvedTarget" }
    git -C (Join-Path $scopeRoot 'v42_root_lp_compression_pr') worktree remove $resolvedTarget
    if ($LASTEXITCODE -ne 0 -or (Test-Path -LiteralPath $resolvedTarget)) { throw "Worktree removal incomplete: $resolvedTarget" }
    $deleted += [pscustomobject]@{path=$resolvedTarget;logical_file_bytes_deleted=$actualBytes;files_deleted=$actualFiles.Count;head=$targetHead;verified_absent=$true}
}
$receipt = [pscustomobject]@{deleted=$deleted;total_logical_file_bytes_deleted=($deleted | Measure-Object -Property logical_file_bytes_deleted -Sum).Sum;files_deleted=($deleted | Measure-Object -Property files_deleted -Sum).Sum;scope='Measured logical file lengths of validated manifest targets; not a guessed physical disk free-space delta';IEEE8500_deleted=$false;WSL_storage_touched=$false}
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $planDirectory 'WINDOWS_ACTUAL_DELETE_RECEIPT.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 6
