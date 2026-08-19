@echo off
setlocal
chcp 65001 >nul
title EDI BIBI - gerador de .edi

rem Entra na pasta onde este .bat esta, nao importa de onde ele foi chamado
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ==========================================================
echo   EDI BIBI - gerador de arquivos .edi
echo   Pasta: %CD%
echo ==========================================================
echo.

if not exist "edi_bibi.py" (
    echo [ERRO] edi_bibi.py nao encontrado nesta pasta.
    echo        Deixe este .bat na mesma pasta do edi_bibi.py.
    goto :fim
)

rem ---------- localiza o Python ----------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    python3 --version >nul 2>&1 && set "PY=python3"
)
if not defined PY (
    echo [ERRO] Python nao encontrado no PATH.
    echo        Baixe em https://www.python.org/downloads/ e marque
    echo        "Add python.exe to PATH" durante a instalacao.
    goto :fim
)

rem ---------- garante a dependencia pdfplumber ----------
%PY% -c "import pdfplumber" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando a dependencia pdfplumber, aguarde...
    %PY% -m pip install pdfplumber
    %PY% -c "import pdfplumber" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [ERRO] Nao foi possivel instalar o pdfplumber.
        echo        Rode manualmente:  %PY% -m pip install pdfplumber
        goto :fim
    )
    echo [OK] pdfplumber instalado.
    echo.
)

rem ---------- confere se ha PDF na pasta ----------
set "TEM_PDF="
for %%F in (*.pdf) do set "TEM_PDF=1"
if not defined TEM_PDF (
    echo [AVISO] Nenhum PDF nesta pasta.
    echo         Copie as ordens de compra em PDF para ca e rode de novo.
    goto :fim
)

rem ---------- executa ----------
%PY% edi_bibi.py

echo.
echo ==========================================================
echo   Concluido. Cada PDF virou uma subpasta com o .edi dentro.
echo ==========================================================

:fim
echo.
pause
endlocal
