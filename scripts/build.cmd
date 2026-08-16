@echo off
REM 构建 VideoSlim 应用程序

REM 设置构建目录
set BUILD_DIR=output
set DIST_DIR=%BUILD_DIR%\dist
set BUILD_TMP_DIR=%BUILD_DIR%\build

REM 创建构建目录（如果不存在）
mkdir %BUILD_DIR% 2>nul

REM 使用 pyinstaller 构建单文件应用，包含所有工具
pyinstaller --onefile ^
    --name "VideoSlim" ^
    --noconsole ^
    --icon "./tools/icon.ico" ^
    --add-data "./tools/ffmpeg.exe;tools" ^
    --add-data "./tools/icon.ico;tools" ^
    --distpath %DIST_DIR% ^
    --workpath %BUILD_TMP_DIR% ^
    main.py

REM 检查构建是否成功
if %ERRORLEVEL% NEQ 0 (
    echo 构建失败！
    exit /b 1
)

echo build success! executable file is located at: %DIST_DIR%\VideoSlim.exe

REM 复制配置文件和其他必要文件到输出目录
copy /Y config.json %DIST_DIR% 2>nul

REM 清理临时文件（可选）
REM rmdir /S /Q %BUILD_TMP_DIBuild 

pause
