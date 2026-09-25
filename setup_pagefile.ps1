# 以管理员身份运行本脚本：在 D:\pagefile.sys 创建 初始16GB / 最大24GB 的预分配分页文件
# 作用：为 14B 本地大模型提供稳定的 OOM swap 兜底（不再瞬时崩溃）
# 运行后需重启电脑生效。

$ErrorActionPreference = 'Stop'

$cs = Get-CimInstance -ClassName Win32_ComputerSystem
$cs.AutomaticManagedPagefile = $false
Set-CimInstance -InputObject $cs

# 查找 D 盘现有分页文件实例；没有就创建（而不是直接报错）
$pf = Get-CimInstance -ClassName Win32_PageFileSetting | Where-Object { $_.Name -match 'D:' }
if (-not $pf) {
    Write-Host "未找到 D 盘分页文件实例，正在创建..." -ForegroundColor Yellow
    try {
        $pf = New-CimInstance -ClassName Win32_PageFileSetting `
            -Property @{ Name = 'D:\pagefile.sys'; InitialSize = 16384; MaximumSize = 24576 } `
            -PassThru
    } catch {
        # 某些系统 New-CimInstance 不被支持，回退到 Set-WmiInstance 创建
        $pf = Set-WmiInstance -Class Win32_PageFileSetting `
            -Arguments @{ Name = 'D:\pagefile.sys'; InitialSize = 16384; MaximumSize = 24576 }
    }
} else {
    $pf.InitialSize = 16384   # 16 GB 预分配
    $pf.MaximumSize = 24576   # 24 GB 上限（比物理内存大，留余量）
    Set-CimInstance -InputObject $pf
}

Write-Host "已设置 D:\pagefile.sys：初始 16GB / 最大 24GB。" -ForegroundColor Green
Write-Host "请重启电脑使设置生效。" -ForegroundColor Yellow
Read-Host -Prompt "按回车退出"
