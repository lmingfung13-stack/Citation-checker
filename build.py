import PyInstaller.__main__
import shutil
import os
import sys
import subprocess
from PyInstaller.utils.hooks import copy_metadata

# 確保在正確的目錄
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("🚀 開始打包程序...")

# 0. 嘗試強制關閉可能還在背景執行的舊版程式
try:
    subprocess.run(['taskkill', '/F', '/IM', 'CitationChecker.exe'], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("   - 系統檢查：已嘗試清除背景殘留的程式")
except Exception:
    pass

# 1. 清理舊的建置資料夾
if os.path.exists("dist"):
    try:
        shutil.rmtree("dist")
        print("   - 已清理舊的 dist 資料夾")
    except Exception as e:
        print(f"   ⚠️ 無法清理 dist 資料夾 ({e})")
        
if os.path.exists("build"):
    try:
        shutil.rmtree("build")
        print("   - 已清理舊的 build 資料夾")
    except Exception as e:
        pass

# 2. 準備 PyInstaller 參數
streamlit_metadata = copy_metadata('streamlit')

pyinstaller_args = [
    'run.py',
    '--name=CitationChecker',
    '--onefile',
    '--clean',
    '--noconsole',  # 開發時建議先不關閉黑視窗，確認執行穩定後再開啟
    
    # 核心檔案
    '--add-data=app.py;.',
    '--add-data=citation_core.py;.',
    
    # 隱藏匯入 (加入 tqdm 以確保 docx2pdf 正常運作)
    '--hidden-import=streamlit',
    '--hidden-import=pandas',
    '--hidden-import=fitz',          
    '--hidden-import=docx2pdf',      
    '--hidden-import=docx',          
    '--hidden-import=pdfplumber',
    '--hidden-import=tqdm',          # 關鍵：docx2pdf 依賴此套件
    '--hidden-import=win32timezone',
    '--hidden-import=pythoncom',
    '--hidden-import=pywintypes',
    
    '--collect-all=streamlit',
]

for src, dest in streamlit_metadata:
    pyinstaller_args.append(f'--add-data={src};{dest}')

# 3. 執行打包
print("   - 正在分析並打包檔案 (需時約 1-2 分鐘)...")
try:
    PyInstaller.__main__.run(pyinstaller_args)
    print("\n" + "="*30)
    if os.path.exists("dist/CitationChecker.exe"):
        print("✅ 打包成功！")
        print(f"📁 您的執行檔位於: {os.path.abspath('dist/CitationChecker.exe')}")
    else:
        print("❌ 打包似乎失敗了，找不到執行檔。")
    print("="*30)
except Exception as e:
    print(f"\n❌ 打包過程發生嚴重錯誤: {e}")