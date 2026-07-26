pyinstaller --onefile --windowed --name MazeHub ^ REM--icon "MAZE_HOUDINI_3_TRAN.ico" ^
  --add-data ".\.pipeline_mirror\pipeline\mazehub\styles.qss;." ^
  main.py