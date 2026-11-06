[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location (Split-Path -Parent $PSScriptRoot)
$py = "python"
if (Test-Path ".\.venv\Scripts\python.exe") { $py = ".\.venv\Scripts\python.exe" }

function Run-Py {
    & $py @args 2>&1 | ForEach-Object { Write-Host $_ }
}

$diamond = ".\tests\test_repo4.txt"
$cycleRepo = ".\tests\test_repo3.txt"
$deepRepo = ".\tests\test_repo5.txt"
$registry = "https://registry.npmjs.org"

Write-Host "`n--- 1. Обратные зависимости для D в ромбовидном графе ---"
Run-Py src/Main.py --package D --repo $diamond --test-mode true --version 1.0.0 --output graph.svg --reverse true

Write-Host "`n--- 2. Обратные зависимости для корня A (нет зависимых) ---"
Run-Py src/Main.py --package A --repo $diamond --test-mode true --version 1.0.0 --output graph.svg --reverse true

Write-Host "`n--- 3. Обратные зависимости в цепочке для E ---"
Run-Py src/Main.py --package E --repo $deepRepo --test-mode true --version 1.0.0 --output graph.svg --reverse true

Write-Host "`n--- 4. Обратные зависимости в циклическом графе для B ---"
Run-Py src/Main.py --package B --repo $cycleRepo --test-mode true --version 1.0.0 --output graph.svg --reverse true

Write-Host "`n--- 5. Ошибка: обратные зависимости только в тестовом режиме ---"
Run-Py src/Main.py --package chalk --repo $registry --test-mode false --version latest --output graph.svg --reverse true

Write-Host "`n--- 6. Ошибка источника: пакета нет в тестовом репозитории ---"
Run-Py src/Main.py --package ZZ --repo $diamond --test-mode true --version 1.0.0 --output graph.svg --reverse true

Write-Host "`n--- 7. Ошибка --reverse: значение не true/false ---"
Run-Py src/Main.py --package D --repo $diamond --test-mode true --version 1.0.0 --output graph.svg --reverse maybe
