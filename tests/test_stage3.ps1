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
$temp = Join-Path $env:TEMP "depgraph_tests"
New-Item -ItemType Directory -Force $temp | Out-Null

$broken = Join-Path $temp "repo_broken.txt"
Set-Content -Path $broken -Encoding ASCII -Value @("A: B", "b: C")

Write-Host "`n--- 1. Граф из тестового репозитория, корень A ---"
Run-Py src/Main.py --package A --repo $diamond --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 2. Подграф от пакета B ---"
Run-Py src/Main.py --package B --repo $diamond --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 3. Цепочка из пяти пакетов от корня A ---"
Run-Py src/Main.py --package A --repo $deepRepo --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 4. Циклическая зависимость A -> B -> C -> A ---"
Run-Py src/Main.py --package A --repo $cycleRepo --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 5. Пакет, зависящий сам от себя ---"
Run-Py src/Main.py --package S --repo $deepRepo --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 6. Ошибка источника: пакета нет в тестовом репозитории ---"
Run-Py src/Main.py --package ZZ --repo $diamond --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 7. Ошибка источника: неверное имя пакета в файле ---"
Run-Py src/Main.py --package A --repo $broken --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 8. Ошибка --repo: файл тестового репозитория не найден ---"
Run-Py src/Main.py --package A --repo .\tests\missing.txt --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 9. Ошибка --package: строчные буквы в тестовом режиме ---"
Run-Py src/Main.py --package abc --repo $diamond --test-mode true --version 1.0.0 --output graph.svg

Write-Host "`n--- 10. Реестр npm: реальный пакет debug 4.4.3 ---"
Run-Py src/Main.py --package debug --repo https://registry.npmjs.org --test-mode false --version 4.4.3 --output graph.svg
