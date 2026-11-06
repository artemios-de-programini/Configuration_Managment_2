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

Remove-Item -Force graph.svg, graph.dot, cycle.svg, cycle.dot, deep.svg, deep.dot, self.svg, self.dot, custom.svg, custom.dot -ErrorAction SilentlyContinue

Write-Host "`n--- 1. Ромбовидный граф: DOT, SVG и ASCII-дерево ---"
Run-Py src/Main.py --package A --repo $diamond --test-mode true --version 1.0.0 --output graph.svg --ascii-tree true
Write-Host ("файлы созданы: " + (Test-Path graph.svg) + " / " + (Test-Path graph.dot))

Write-Host "`n--- 2. Циклический граф: пометки циклов в выводе ---"
Run-Py src/Main.py --package A --repo $cycleRepo --test-mode true --version 1.0.0 --output cycle.svg --ascii-tree true

Write-Host "`n--- 3. Цепочка из пяти пакетов с ASCII-деревом ---"
Run-Py src/Main.py --package A --repo $deepRepo --test-mode true --version 1.0.0 --output deep.svg --ascii-tree true

Write-Host "`n--- 4. Пакет, зависящий сам от себя ---"
Run-Py src/Main.py --package S --repo $deepRepo --test-mode true --version 1.0.0 --output self.svg --ascii-tree true

Write-Host "`n--- 5. Своё имя файла изображения ---"
Run-Py src/Main.py --package D --repo $diamond --test-mode true --version 1.0.0 --output custom.svg
Write-Host ("custom.svg создан: " + (Test-Path custom.svg) + ", custom.dot создан: " + (Test-Path custom.dot))

Write-Host "`n--- 6. Реестр npm: chalk с ASCII-деревом ---"
Run-Py src/Main.py --package chalk --repo $registry --test-mode false --version latest --output graph.svg --ascii-tree true

Write-Host "`n--- 7. Ошибка --output: путь вместо имени файла ---"
Run-Py src/Main.py --package A --repo $diamond --test-mode true --version 1.0.0 --output out/graph.svg

Write-Host "`n--- 8. Ошибка --output: расширение не .svg ---"
Run-Py src/Main.py --package A --repo $diamond --test-mode true --version 1.0.0 --output graph.png

Write-Host "`n--- 9. Ошибка источника: пакета нет в тестовом репозитории ---"
Run-Py src/Main.py --package ZZ --repo $diamond --test-mode true --version 1.0.0 --output graph.svg
