[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location (Split-Path -Parent $PSScriptRoot)
$py = "python"
if (Test-Path ".\.venv\Scripts\python.exe") { $py = ".\.venv\Scripts\python.exe" }

function Run-Py {
    & $py @args 2>&1 | ForEach-Object { Write-Host $_ }
}

$registry = "https://registry.npmjs.org"

Write-Host "`n--- 1. Пакет без зависимостей: chalk ---"
Run-Py src/Main.py --package chalk --repo $registry --test-mode false --version latest --output graph.svg

Write-Host "`n--- 2. Пакет с зависимостью: debug 4.4.3 ---"
Run-Py src/Main.py --package debug --repo $registry --test-mode false --version 4.4.3 --output graph.svg

Write-Host "`n--- 3. Пакет с большим числом зависимостей: express 4.19.2 ---"
Run-Py src/Main.py --package express --repo $registry --test-mode false --version 4.19.2 --output graph.svg

Write-Host "`n--- 4. Ошибка реестра: пакета нет в реестре ---"
Run-Py src/Main.py --package no-such-package-xyz-2026 --repo $registry --test-mode false --version 1.0.0 --output graph.svg

Write-Host "`n--- 5. Ошибка реестра: версия не найдена ---"
Run-Py src/Main.py --package chalk --repo $registry --test-mode false --version 99.99.99 --output graph.svg

Write-Host "`n--- 6. Тестовый режим на этом этапе ещё не реализован ---"
Run-Py src/Main.py --package A --repo README.md --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 7. Ошибка --package: недопустимое имя пакета npm ---"
Run-Py src/Main.py --package Bad_Name --repo $registry --test-mode false --version 1.0.0 --output graph.svg

Write-Host "`n--- 8. Ошибка --repo: некорректный адрес реестра ---"
Run-Py src/Main.py --package chalk --repo not-a-url --test-mode false --version 1.0.0 --output graph.svg

Write-Host "`n--- 9. Ошибка --version: неверный формат версии ---"
Run-Py src/Main.py --package chalk --repo $registry --test-mode false --version 1.0 --output graph.svg

Write-Host "`n--- 10. Ошибка --output: расширение не .svg ---"
Run-Py src/Main.py --package chalk --repo $registry --test-mode false --version 1.0.0 --output graph.png

Write-Host "`n--- 11. Ошибка --test-mode: значение не true/false ---"
Run-Py src/Main.py --package chalk --repo $registry --test-mode maybe --version 1.0.0 --output graph.svg

Write-Host "`n--- 12. Ошибка разбора: не заданы обязательные параметры ---"
Run-Py src/Main.py --package chalk
