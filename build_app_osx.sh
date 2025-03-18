#!/bin/bash

source env/bin/activate

echo "🧹 Очистка временных файлов..."
rm -rf build dist
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete
find . -type f -name "*.pyd" -delete
find . -type f -name ".DS_Store" -delete

echo "🧹 Удаление директорий .dist-info и .egg-info..."
find . -type d -name "*.dist-info" -exec rm -rf {} +
find . -type d -name "*.egg-info" -exec rm -rf {} +


echo "📦 Сборка приложения..."
python3.11 setup.py py2app && echo "✅ Сборка завершена"

deactivate 