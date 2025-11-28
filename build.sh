#!/bin/bash

# Остановка при любой ошибке
set -e

# Цвета для вывода
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Определяем среду (CI или локально)
IS_CI=false
if [ "$GITHUB_ACTIONS" == "true" ]; then
    IS_CI=true
fi

echo -e "${CYAN}--- Starting Build Process (Linux) ---${NC}"

if [ "$IS_CI" = true ]; then
    echo -e "${CYAN}Environment: GitHub Actions (Clean Install)${NC}"
else
    echo -e "${CYAN}Environment: Local Machine${NC}"
fi

# --- ФУНКЦИЯ ПРОВЕРКИ ЗАВИСИМОСТЕЙ ---
ensure_package() {
    PKG_NAME=$1
    IMPORT_NAME=$2

    if [ "$IS_CI" = true ]; then
        echo "CI: Installing $PKG_NAME..."
        pip install "$PKG_NAME"
        return
    fi

    # Проверка импорта в Python
    if python -c "import $IMPORT_NAME" &> /dev/null; then
        echo -e "Checking $PKG_NAME... ${GREEN}OK (Already installed)${NC}"
    else
        echo -e "Checking $PKG_NAME... ${YELLOW}MISSING. Installing...${NC}"
        # В Arch Linux лучше использовать pacman, но для скрипта используем pip
        # Если вы не в venv, добавьте --break-system-packages (на свой страх и риск) 
        # или используйте виртуальное окружение.
        pip install "$PKG_NAME"
    fi
}

# 1. Build Tools
ensure_package "pyinstaller" "PyInstaller"
ensure_package "Pillow" "PIL"

# 2. Project Dependencies
if [ "$IS_CI" = true ]; then
    if [ -f "requirements.txt" ]; then
        echo "CI: Installing dependencies from requirements.txt..."
        pip install -r requirements.txt
    fi
else
    echo -e "${CYAN}Local: Skipping requirements.txt install (assuming dev env is ready).${NC}"
fi

# 3. Icon Handling
# В Linux конвертация в .ico не обязательна для самого бинарника,
# но если код ссылается на assets/icon.png, он должен там быть.
if [ ! -f "assets/icon.png" ]; then
    echo -e "${YELLOW}Warning: assets/icon.png not found!${NC}"
fi

# 4. Cleanup
if [ -d "dist" ]; then rm -rf dist; fi
if [ -d "build" ]; then rm -rf build; fi
if [ -f *.spec ]; then rm -f *.spec; fi

# 5. Build
echo -e "${CYAN}Running PyInstaller...${NC}"

# ВАЖНО: Разделитель в --add-data для Linux это ДВОЕТОЧИЕ (:), а не точка с запятой (;)
# Флаг --icon в Linux мало на что влияет для самого бинарника, но можно оставить png
pyinstaller --noconfirm --onefile --windowed --clean \
    --name "Open4KEditor" \
    --add-data "assets:assets" \
    main.py

# 6. Verify
# В Linux у файла нет расширения .exe
BINARY_PATH="dist/Open4KEditor"

if [ -f "$BINARY_PATH" ]; then
    echo -e "${GREEN}SUCCESS: Build complete.${NC}"
    echo "File: $BINARY_PATH"
    
    # Делаем файл исполняемым (на всякий случай)
    chmod +x "$BINARY_PATH"
else
    echo -e "${RED}ERROR: Output file not found!${NC}"
    exit 1
fi