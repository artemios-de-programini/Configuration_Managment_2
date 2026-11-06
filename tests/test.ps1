[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location (Split-Path -Parent $PSScriptRoot)
$py = "python"
if (Test-Path ".\.venv\Scripts\python.exe") { $py = ".\.venv\Scripts\python.exe" }

function Run-Py {
    & $py @args 2>&1 | ForEach-Object { Write-Host $_ }
}

$registry = "https://registry.npmjs.org"

Write-Host "`n--- 1. Корректный запуск: express из реестра npm ---"
Run-Py src/Main.py --package express --repo $registry --test-mode false --version 4.19.2 --output graph.svg

Write-Host "`n--- 2. Корректный запуск с выводом ASCII-дерева ---"
Run-Py src/Main.py --package express --repo $registry --test-mode false --version latest --output graph.svg --ascii-tree true

Write-Host "`n--- 3. Тестовый режим: существующий файл репозитория ---"
Run-Py src/Main.py --package AB --repo README.md --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 4. Ошибка --package: имя пакета не задано ---"
Run-Py src/Main.py --package="" --repo README.md --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 5. Ошибка --package: недопустимое имя пакета npm ---"
Run-Py src/Main.py --package Bad_Name --repo $registry --test-mode false --version 1.0.0 --output graph.svg

Write-Host "`n--- 6. Ошибка --package: строчные буквы в тестовом режиме ---"
Run-Py src/Main.py --package abc --repo README.md --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 7. Ошибка --repo: некорректный адрес реестра ---"
Run-Py src/Main.py --package express --repo not-a-url --test-mode false --version 1.0.0 --output graph.svg

Write-Host "`n--- 8. Ошибка --repo: файл тестового репозитория не найден ---"
Run-Py src/Main.py --package AB --repo missing.txt --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 9. Ошибка --version: неверный формат версии ---"
Run-Py src/Main.py --package express --repo $registry --test-mode false --version 1.0 --output graph.svg

Write-Host "`n--- 10. Ошибка --output: расширение не .svg ---"
Run-Py src/Main.py --package express --repo $registry --test-mode false --version 1.0.0 --output graph.png

Write-Host "`n--- 11. Ошибка --output: путь вместо имени файла ---"
Run-Py src/Main.py --package express --repo $registry --test-mode false --version 1.0.0 --output out/graph.svg

Write-Host "`n--- 12. Ошибка --test-mode: значение не true/false ---"
Run-Py src/Main.py --package express --repo $registry --test-mode maybe --version 1.0.0 --output graph.svg

Write-Host "`n--- 13. Ошибка разбора: не задан обязательный параметр ---"
Run-Py src/Main.py --package express
