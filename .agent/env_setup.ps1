# AutoAgent Test Agent 环境初始化
# 每次 shell 启动时自动执行

# 1. GitHub CLI PATH
$ghPath = "C:\Program Files\GitHub CLI"
if ($env:Path -notlike "*$ghPath*") {
    $env:Path += ";$ghPath"
}

# 2. 加载认证
$envFile = "C:\Users\xsl\.autovt\test.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^(\w+)=(.+)$') {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
        }
    }
}

# 3. Git 身份
git config user.name "gaobiedongtian"
git config user.email "gaobiedongtian@163.com"

Write-Host "Test Agent environment initialized. gh: $(gh --version 2>&1 | Select-Object -First 1)"
