# Установка Tesseract OCR и Poppler

Для работы функции распознавания сканированных PDF-документов необходимо установить Tesseract OCR и Poppler в системе.

## macOS

### Через Homebrew (рекомендуется)

1. Установите Homebrew (если ещё не установлен):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

2. Установите Tesseract с языковыми пакетами:
```bash
brew install tesseract tesseract-lang
```

3. Установите Poppler (для конвертации PDF в изображения):
```bash
brew install poppler
```

### Через MacPorts

```bash
sudo port install tesseract tesseract-rus tesseract-eng poppler
```

## Linux (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng poppler-utils
```

## Linux (Fedora/RHEL)

```bash
sudo dnf install tesseract tesseract-langpack-rus tesseract-langpack-eng poppler-utils
```

## Проверка установки

После установки проверьте, что Tesseract доступен:

```bash
tesseract --version
```

Должна отобразиться версия Tesseract и список доступных языков.

## Python-зависимости

После установки системных пакетов установите Python-библиотеки:

```bash
pip install pytesseract pdf2image Pillow
```

## Проверка работоспособности

Запустите тест:

```bash
cd /path/to/web_interface
python3 -c "
from document_processor.pdf_reader import PdfReader
reader = PdfReader()
result = reader.read_pdf('test.pdf', ocr='force')
print(f'Текст извлечён: {len(result[\"text\"])} символов')
"
```

## Возможные проблемы

### "Tesseract не найден"

Убедитесь, что Tesseract установлен и доступен в PATH:
```bash
which tesseract
```

Если команда не найдена, установите Tesseract по инструкции выше.

### "OCR пропущен: отсутствуют зависимости"

Установите Python-зависимости:
```bash
pip3 install pytesseract pdf2image Pillow
```

### Низкое качество распознавания

1. Убедитесь, что установлены русский и английский языковые пакеты
2. Проверьте качество исходного PDF (разрешение, контрастность)
3. Модуль автоматически пробует разные ориентации изображения (0°, 90°, 180°, 270°)

## Автоматическая коррекция ориентации

Модуль автоматически определяет и исправляет ориентацию документа:
- Пробует 4 варианта поворота (0°, 90°, 180°, 270°)
- Использует OSD (Orientation and Script Detection) если доступно
- Выбирает ориентацию с наибольшим количеством распознанного текста

Эта функция помогает корректно распознавать документы, отсканированные в альбомной ориентации или перевёрнутые.
