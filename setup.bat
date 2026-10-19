@echo off
setlocal
set SCARF_ANALYTICS=false
cd /d "%~dp0"
echo Preparation de PFE Mail Agent...
where python >nul 2>nul || (echo Installez Python 3.11 ou plus et ajoutez-le au PATH. & pause & exit /b 1)
where npm.cmd >nul 2>nul || (echo Installez Node.js 20.19 ou plus. & pause & exit /b 1)
python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 minimum'" || goto :failure
if not exist .venv\Scripts\python.exe python -m venv .venv
if errorlevel 1 goto :failure
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :failure
call npm.cmd --prefix frontend ci --no-audit --no-fund
if errorlevel 1 goto :failure
call npm.cmd run build
if errorlevel 1 goto :failure
if not exist data mkdir data
if not exist .env copy .env.example .env >nul
echo Installation terminee. Lancez start.bat.
pause
exit /b 0
:failure
echo Installation interrompue. Consultez le message ci-dessus.
pause
exit /b 1
