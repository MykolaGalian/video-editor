# Check if PyInstaller is installed
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "PyInstaller not found. Installing..."
    pip install pyinstaller
}

# Install Pillow for icon conversion
Write-Host "Ensuring Pillow is installed..."
pip install Pillow

# Convert PNG to ICO
$iconPng = "assets/icon.png"
$iconIco = "assets/icon.ico"
if (Test-Path $iconPng) {
    Write-Host "Converting icon to .ico..."
    python -c "from PIL import Image; img = Image.open(r'$iconPng'); img.save(r'$iconIco', format='ICO', sizes=[(256, 256)])"
}

# Clean previous build artifacts
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "Open 4K Editor.spec") { Remove-Item -Force "Open 4K Editor.spec" }

# Build the executable
Write-Host "Building executable..."
# --clean: Clean PyInstaller cache
# --windowed: No console window
# --onefile: Single executable
# --add-data: Bundle assets folder
# --icon: Set executable icon
pyinstaller --noconfirm --onefile --windowed --clean --name "Open 4K Editor" --add-data "assets;assets" --icon "assets/icon.ico" main.py

# Post-build steps
if (Test-Path "dist/Open 4K Editor.exe") {
    Write-Host "Build success!"
    
    # Copy ffmpeg.exe if it exists in the root, so the user has it ready
    if (Test-Path "ffmpeg.exe") {
        Write-Host "Copying ffmpeg.exe to dist folder..."
        Copy-Item "ffmpeg.exe" -Destination "dist"
    } else {
        Write-Host "Warning: ffmpeg.exe not found in root. You may need to provide it manually."
    }

    Write-Host "Executable is located in the 'dist' folder."
} else {
    Write-Host "Build failed."
}

Read-Host -Prompt "Press Enter to exit"
