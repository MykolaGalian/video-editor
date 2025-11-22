$ErrorActionPreference = "Stop"

# Определяем, где мы запущены: в GitHub Actions или локально
$isCI = [bool]$env:GITHUB_ACTIONS

Write-Host "--- Starting Build Process ---"
if ($isCI) { Write-Host "Environment: GitHub Actions (Clean Install)" -ForegroundColor Cyan }
else { Write-Host "Environment: Local Machine (Smart Check)" -ForegroundColor Cyan }

# --- ФУНКЦИЯ ПРОВЕРКИ ---
# Проверяет, установлен ли модуль Python. Если нет — устанавливает.
function Ensure-Package ($packageName, $importName) {
    # Если мы в CI, всегда устанавливаем
    if ($isCI) {
        Write-Host "CI: Installing $packageName..."
        pip install $packageName
        return
    }

    # Локально проверяем через Python import
    Write-Host "Checking $packageName..." -NoNewline
    python -c "import $importName" 2>$null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK (Already installed)" -ForegroundColor Green
    } else {
        Write-Host " MISSING. Installing..." -ForegroundColor Yellow
        pip install $packageName
    }
}

# 1. Build Tools
# Проверяем 'pyinstaller' (пакет) по импорту 'PyInstaller' (модуль)
Ensure-Package "pyinstaller" "PyInstaller"
# Проверяем 'Pillow' (пакет) по импорту 'PIL' (модуль)
Ensure-Package "Pillow" "PIL"

# 2. Project Dependencies (requirements.txt)
if ($isCI) {
    # В GitHub Actions ставим зависимости всегда
    if (Test-Path "requirements.txt") {
        Write-Host "CI: Installing dependencies from requirements.txt..."
        pip install -r requirements.txt
    }
} else {
    # Локально мы предполагаем, что среда уже настроена.
    # Но если хотите, можно раскомментировать строку ниже, чтобы pip проверил их (это обычно быстро)
    # pip install -r requirements.txt
    Write-Host "Local: Skipping requirements.txt install (assuming dev env is ready)." -ForegroundColor DarkGray
}

# 3. Convert Icon
$iconPng = "assets/icon.png"
$iconIco = "assets/icon.ico"
if (Test-Path $iconPng) {
    # Конвертируем иконку только если её нет или если мы в CI (чтобы обновить)
    if ($isCI -or (-not (Test-Path $iconIco))) {
        Write-Host "Converting icon to .ico..."
        python -c "from PIL import Image; img = Image.open(r'$iconPng'); img.save(r'$iconIco', format='ICO', sizes=[(256, 256)])"
    } else {
        Write-Host "Icon already exists. Skipping conversion." -ForegroundColor DarkGray
    }
}

# 4. Cleanup (Чистим старое)
# Локально можно не чистить так агрессивно, но для надежности сборки лучше оставить
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "*.spec") { Remove-Item -Force "*.spec" }

# 5. Build
Write-Host "Running PyInstaller..."
pyinstaller --noconfirm --onefile --windowed --clean --name "Open 4K Editor" --add-data "assets;assets" --icon "assets/icon.ico" main.py --log-level WARN

# 6. Verify
if (Test-Path "dist/Open 4K Editor.exe") {
    Write-Host "SUCCESS: Build complete." -ForegroundColor Green
    Write-Host "File: dist/Open 4K Editor.exe"
} else {
    Write-Host "ERROR: Output file not found!" -ForegroundColor Red
    exit 1
}

if (-not $isCI) {
    Read-Host -Prompt "Press Enter to exit"
}