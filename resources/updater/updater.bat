@echo off
rem typetype 平台更新器（Windows，ADR-014 决策 5）
rem
rem 用法: updater.bat <install_dir> <stage_dir>
rem   install_dir  当前安装目录（含旧版可执行文件与依赖）
rem   stage_dir    已下载并解压好的新版目录（临时）
rem
rem 流程: 备份旧目录 -> 新版替换 -> 删除备份 -> 重启应用 -> 退出
rem 幂等/失败保留: 任一步失败即中止，旧目录以 .bak 保留。

setlocal

set "INSTALL_DIR=%~1"
set "STAGE_DIR=%~2"
set "BACKUP_DIR=%INSTALL_DIR%.bak"

if "%INSTALL_DIR%"=="" (
  echo usage: updater.bat install_dir stage_dir
  exit /b 2
)
if "%STAGE_DIR%"=="" (
  echo usage: updater.bat install_dir stage_dir
  exit /b 2
)
if not exist "%STAGE_DIR%" (
  echo stage dir not found: %STAGE_DIR%
  exit /b 1
)
if not exist "%INSTALL_DIR%" (
  echo install dir not found: %INSTALL_DIR%
  exit /b 1
)

rem 1) 备份旧目录（同名 .bak；若已有备份先移除旧备份）
if exist "%BACKUP_DIR%" rmdir /s /q "%BACKUP_DIR%"
move /y "%INSTALL_DIR%" "%BACKUP_DIR%" >nul
if errorlevel 1 (
  echo backup failed
  exit /b 1
)

rem 2) 新版替换到安装目录（robocopy 优先，缺失时 xcopy 兜底）
robocopy "%STAGE_DIR%" "%INSTALL_DIR%" /E /MOVE /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
  rem robocopy 返回码 >=8 才是错误；回滚旧目录
  move /y "%BACKUP_DIR%" "%INSTALL_DIR%" >nul 2>nul
  echo replace failed, rolled back
  exit /b 1
)
if not exist "%INSTALL_DIR%" (
  xcopy "%STAGE_DIR%" "%INSTALL_DIR%" /E /I /Q /Y >nul 2>nul
  if errorlevel 1 (
    move /y "%BACKUP_DIR%" "%INSTALL_DIR%" >nul 2>nul
    echo replace failed, rolled back
    exit /b 1
  )
)

rem 3) 删除备份
rmdir /s /q "%BACKUP_DIR%" >nul 2>nul

rem 4) 重启应用（detach，后台启动）
set "RESTART_BIN=%INSTALL_DIR%\typetype.exe"
if not exist "%RESTART_BIN%" (
  rem Nuitka standalone 产物主程序名与入口脚本名一致（main -> main.exe）；逐一探测
  for %%F in (typetype.exe main.exe) do (
    if exist "%INSTALL_DIR%\%%F" set "RESTART_BIN=%INSTALL_DIR%\%%F"
  )
)
if exist "%RESTART_BIN%" (
  start "" "%RESTART_BIN%"
) else (
  echo executable not found, please start %INSTALL_DIR% manually
)

exit /b 0
