param([Parameter(Mandatory=$true)][string]$Phase)
$ErrorActionPreference='Stop'
if (-not ('RollbackAllocatedFileSize' -as [type])) {
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class RollbackAllocatedFileSize {
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern uint GetCompressedFileSizeW(string path, out uint high);
  [DllImport("kernel32.dll")]
  public static extern void SetLastError(uint error);
  public static ulong Bytes(string path) {
    uint high; SetLastError(0);
    uint low=GetCompressedFileSizeW(path,out high);
    int error=Marshal.GetLastWin32Error();
    if(low==UInt32.MaxValue && error!=0) throw new System.ComponentModel.Win32Exception(error);
    return ((ulong)high << 32) | low;
  }
}
'@
}
$registry=@(Get-ChildItem -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' | ForEach-Object {Get-ItemProperty -LiteralPath $_.PSPath} | Where-Object DistributionName -eq 'Ubuntu-MobileESS-D')
if($registry.Count -ne 1){throw 'Exact registry entry required'}
$base=$registry[0].BasePath
if($base.StartsWith('\\?\')){$base=$base.Substring(4)}
$vhd=[IO.Path]::GetFullPath((Join-Path $base 'ext4.vhdx'))
if($vhd -ne 'D:\WSL\Ubuntu-MobileESS-D\ext4.vhdx'){throw 'Unexpected VHD'}
$row=[pscustomobject]@{phase=$Phase;timestamp=(Get-Date).ToUniversalTime().ToString('o');verified_vhd_path=$vhd;VHDX_file_length=(Get-Item -LiteralPath $vhd).Length;VHDX_physical_allocated_bytes=[RollbackAllocatedFileSize]::Bytes($vhd);C_free_bytes=([IO.DriveInfo]::new('C:\')).AvailableFreeSpace;D_free_bytes=([IO.DriveInfo]::new('D:\')).AvailableFreeSpace;physical_measurement='GetCompressedFileSizeW; actual allocated storage, separately from file length'}
$row | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('HOST_SPACE_'+$Phase+'.json')) -Encoding UTF8
$row | ConvertTo-Json
